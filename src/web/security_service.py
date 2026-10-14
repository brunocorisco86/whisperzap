"""Serviço de Segurança Administrativa, Troca de Senha e Autenticação FIDO2 / WebAuthn."""

import os
import time
import secrets
import hashlib
import logging
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from src.config import settings
from src.memory.models import AdminSettingRecord, Fido2CredentialRecord

logger = logging.getLogger(__name__)

# Cache de desafios ativos em memória (challenge_b64url -> (purpose, expires_at))
_ACTIVE_CHALLENGES: Dict[str, Tuple[str, float]] = {}
CHALLENGE_TTL_SECONDS = 300.0  # 5 minutos


def _clean_expired_challenges():
    """Remove desafios expirados do cache em memória."""
    now = time.time()
    expired = [k for k, (_, exp) in _ACTIVE_CHALLENGES.items() if now > exp]
    for k in expired:
        _ACTIVE_CHALLENGES.pop(k, None)


class SecurityService:
    """Gerenciador central de credenciais administrativas e chaves de hardware FIDO2."""

    def __init__(self):
        self.default_user_id = b"bruno_mnemosine_owner"
        self.default_user_name = "bruno"
        self.default_display_name = "Bruno Conter (Owner)"

    # =========================================================================
    # 1. GESTÃO DE SENHA MESTRA (PBKDF2-SHA256)
    # =========================================================================

    def verify_password(self, password: str, db: Session) -> bool:
        """Verifica a senha informada contra o hash persistido no banco ou o fallback do .env."""
        if not settings.DASHBOARD_AUTH_ENABLED:
            return True

        if not password:
            return False

        try:
            hash_rec = db.query(AdminSettingRecord).filter(AdminSettingRecord.key == "dashboard_password_hash").first()
            salt_rec = db.query(AdminSettingRecord).filter(AdminSettingRecord.key == "dashboard_password_salt").first()

            if hash_rec and salt_rec and hash_rec.value and salt_rec.value:
                salt_bytes = bytes.fromhex(salt_rec.value)
                calc_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 100_000).hex()
                return secrets.compare_digest(calc_hash, hash_rec.value)

            # Fallback para a senha padrão configurada no ambiente
            return secrets.compare_digest(password, settings.DASHBOARD_PASSWORD)
        except Exception as exc:
            logger.error(f"Erro ao verificar senha no banco: {exc}")
            return secrets.compare_digest(password, settings.DASHBOARD_PASSWORD)

    def change_password(self, current_password: str, new_password: str, db: Session) -> Tuple[bool, str]:
        """Valida a senha atual e persiste a nova senha com salt criptográfico de 128 bits."""
        if not self.verify_password(current_password, db):
            return False, "Senha atual incorreta."

        if not new_password or len(new_password) < 4:
            return False, "A nova senha deve ter pelo menos 4 caracteres."

        try:
            salt_bytes = secrets.token_bytes(16)
            salt_hex = salt_bytes.hex()
            new_hash = hashlib.pbkdf2_hmac("sha256", new_password.encode("utf-8"), salt_bytes, 100_000).hex()

            # Salva ou atualiza no banco
            for key, val in [("dashboard_password_hash", new_hash), ("dashboard_password_salt", salt_hex)]:
                rec = db.query(AdminSettingRecord).filter(AdminSettingRecord.key == key).first()
                if not rec:
                    rec = AdminSettingRecord(key=key, value=val)
                    db.add(rec)
                else:
                    rec.value = val
            db.commit()
            logger.info("🔐 Senha mestra do dashboard alterada e persistida com sucesso no PostgreSQL.")
            return True, "Senha alterada com sucesso."
        except Exception as exc:
            db.rollback()
            logger.error(f"Erro ao alterar senha no PostgreSQL: {exc}")
            return False, f"Erro interno ao persistir nova senha: {exc}"

    # =========================================================================
    # 2. WEBAUTHN / FIDO2 (YubiKey, Pico Key, Passkeys)
    # =========================================================================

    def _resolve_rp_id(self, host_header: Optional[str] = None) -> str:
        """Determina o Relying Party ID apropriado baseado no host da requisição."""
        if host_header:
            clean_host = host_header.split(":")[0].strip()
            if clean_host:
                return clean_host
        if settings.HERMES_DOMAIN:
            clean_domain = settings.HERMES_DOMAIN.split(",")[0].split(":")[0].strip()
            if clean_domain and clean_domain != "80":
                return clean_domain
        return "brunoconter.duckdns.org"

    def _resolve_expected_origin(self, host_header: Optional[str] = None, scheme: str = "https") -> str:
        """Determina a origin esperada para validação estrita WebAuthn."""
        rp_id = self._resolve_rp_id(host_header)
        if rp_id in ["localhost", "127.0.0.1"]:
            port_part = f":{host_header.split(':')[1]}" if host_header and ":" in host_header else ""
            return f"http://{rp_id}{port_part}"
        return f"https://{rp_id}"

    def generate_fido2_registration_options(self, host_header: Optional[str] = None, db: Optional[Session] = None) -> dict:
        """Gera as opções de desafio para registrar uma nova Pico Key / YubiKey."""
        import webauthn
        from webauthn.helpers import bytes_to_base64url
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor

        rp_id = self._resolve_rp_id(host_header)
        _clean_expired_challenges()

        # Evita registrar credencial duplicada
        exclude_credentials = []
        if db:
            existing = db.query(Fido2CredentialRecord.id).all()
            for (cid,) in existing:
                try:
                    from webauthn.helpers import base64url_to_bytes
                    exclude_credentials.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(cid)))
                except Exception:
                    pass

        options = webauthn.generate_registration_options(
            rp_id=rp_id,
            rp_name="Mnemosine Intelligence Hub",
            user_id=self.default_user_id,
            user_name=self.default_user_name,
            user_display_name=self.default_display_name,
            exclude_credentials=exclude_credentials,
        )

        challenge_b64 = bytes_to_base64url(options.challenge)
        _ACTIVE_CHALLENGES[challenge_b64] = ("register", time.time() + CHALLENGE_TTL_SECONDS)

        return webauthn.options_to_json(options)

    def _extract_challenge_from_credential(self, credential_json: str) -> Optional[str]:
        """Extrai o challenge do clientDataJSON do retorno da chave FIDO2."""
        try:
            import json
            import base64
            data = json.loads(credential_json)
            client_data_b64 = data.get("response", {}).get("clientDataJSON")
            if not client_data_b64:
                return None
            padded = client_data_b64 + "=" * (-len(client_data_b64) % 4)
            client_data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
            return client_data.get("challenge")
        except Exception as exc:
            logger.debug(f"Não foi possível extrair challenge do clientDataJSON: {exc}")
            return None

    def verify_fido2_registration(
        self,
        registration_json: str,
        device_name: str,
        host_header: Optional[str] = None,
        scheme: str = "https",
        db: Optional[Session] = None,
    ) -> Tuple[bool, str]:
        """Valida a atestação da chave de hardware FIDO2 e salva no banco de dados."""
        import webauthn
        from webauthn.helpers import bytes_to_base64url

        _clean_expired_challenges()
        rp_id = self._resolve_rp_id(host_header)
        expected_origin = self._resolve_expected_origin(host_header, scheme)

        # Extrai o challenge exato utilizado pelo navegador
        client_challenge = self._extract_challenge_from_credential(registration_json)
        expected_challenge = None

        if client_challenge and client_challenge in _ACTIVE_CHALLENGES:
            purpose, exp = _ACTIVE_CHALLENGES[client_challenge]
            if purpose == "register" and exp > time.time():
                expected_challenge = client_challenge

        if not expected_challenge:
            valid = [c for c, (p, exp) in _ACTIVE_CHALLENGES.items() if p == "register" and exp > time.time()]
            if len(valid) == 1:
                expected_challenge = valid[0]

        if not expected_challenge:
            return False, "Desafio de registro expirou ou não foi encontrado. Tente novamente."

        try:
            from webauthn.helpers import base64url_to_bytes
            verification = webauthn.verify_registration_response(
                credential=registration_json,
                expected_challenge=base64url_to_bytes(expected_challenge),
                expected_origin=expected_origin,
                expected_rp_id=rp_id,
                require_user_verification=False,
            )

            cred_id_b64 = bytes_to_base64url(verification.credential_id)
            pub_key_b64 = bytes_to_base64url(verification.credential_public_key)

            if db:
                cred_rec = Fido2CredentialRecord(
                    id=cred_id_b64,
                    public_key=pub_key_b64,
                    sign_count=verification.sign_count,
                    device_name=device_name or "Pico Key / Hardware Key",
                    transports=[],
                )
                db.merge(cred_rec)
                db.commit()

            logger.info(f"🔑 Chave FIDO2 '{device_name}' cadastrada com sucesso! (ID: {cred_id_b64[:12]}...)")
            return True, "Chave FIDO2 cadastrada com sucesso."
        except Exception as exc:
            logger.error(f"Erro ao verificar registro FIDO2: {exc}")
            return False, f"Falha na validação da chave FIDO2: {exc}"
        finally:
            _ACTIVE_CHALLENGES.pop(expected_challenge, None)

    def generate_fido2_authentication_options(self, host_header: Optional[str] = None, db: Optional[Session] = None) -> dict:
        """Gera as opções de desafio para login com a Pico Key / YubiKey."""
        import webauthn
        from webauthn.helpers import bytes_to_base64url
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

        rp_id = self._resolve_rp_id(host_header)
        _clean_expired_challenges()

        allow_credentials = []
        if db:
            existing = db.query(Fido2CredentialRecord.id).all()
            for (cid,) in existing:
                try:
                    from webauthn.helpers import base64url_to_bytes
                    allow_credentials.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(cid)))
                except Exception:
                    pass

        options = webauthn.generate_authentication_options(
            rp_id=rp_id,
            allow_credentials=allow_credentials if allow_credentials else None,
            user_verification=UserVerificationRequirement.DISCOURAGED,
        )

        challenge_b64 = bytes_to_base64url(options.challenge)
        _ACTIVE_CHALLENGES[challenge_b64] = ("login", time.time() + CHALLENGE_TTL_SECONDS)

        return webauthn.options_to_json(options)

    def verify_fido2_authentication(
        self,
        authentication_json: str,
        host_header: Optional[str] = None,
        scheme: str = "https",
        db: Optional[Session] = None,
    ) -> Tuple[bool, str]:
        """Valida a assinatura física gerada pela chave FIDO2 e autoriza a sessão."""
        import webauthn
        import json

        _clean_expired_challenges()
        rp_id = self._resolve_rp_id(host_header)
        expected_origin = self._resolve_expected_origin(host_header, scheme)

        # Extrai o challenge exato retornado no clientDataJSON
        client_challenge = self._extract_challenge_from_credential(authentication_json)
        expected_challenge = None

        if client_challenge and client_challenge in _ACTIVE_CHALLENGES:
            purpose, exp = _ACTIVE_CHALLENGES[client_challenge]
            if purpose == "login" and exp > time.time():
                expected_challenge = client_challenge

        if not expected_challenge:
            valid = [c for c, (p, exp) in _ACTIVE_CHALLENGES.items() if p == "login" and exp > time.time()]
            if len(valid) == 1:
                expected_challenge = valid[0]

        if not expected_challenge:
            return False, "Desafio de autenticação expirado ou inválido. Tente novamente."

        try:
            from webauthn.helpers import base64url_to_bytes

            auth_data = json.loads(authentication_json)
            cred_id = auth_data.get("id") or auth_data.get("rawId")
            if not cred_id:
                return False, "Identificador da chave não fornecido."

            cred_rec = db.query(Fido2CredentialRecord).filter(Fido2CredentialRecord.id == cred_id).first() if db else None
            if not cred_rec:
                return False, "Chave de segurança não cadastrada no sistema."

            verification = webauthn.verify_authentication_response(
                credential=authentication_json,
                expected_challenge=base64url_to_bytes(expected_challenge),
                expected_origin=expected_origin,
                expected_rp_id=rp_id,
                credential_public_key=base64url_to_bytes(cred_rec.public_key),
                credential_current_sign_count=cred_rec.sign_count,
                require_user_verification=False,
            )

            # Atualiza contador e última utilização
            if db:
                from datetime import datetime, timezone
                cred_rec.sign_count = verification.new_sign_count
                cred_rec.last_used_at = datetime.now(timezone.utc)
                db.commit()

            logger.info(f"🔓 Autenticação FIDO2 bem-sucedida para o dispositivo '{cred_rec.device_name}'!")
            return True, "Autenticação via chave física autorizada com sucesso."
        except Exception as exc:
            logger.error(f"Erro ao verificar autenticação FIDO2: {exc}")
            return False, f"Falha na validação da chave FIDO2: {exc}"
        finally:
            _ACTIVE_CHALLENGES.pop(expected_challenge, None)

    def list_fido2_keys(self, db: Session) -> List[dict]:
        """Lista todas as chaves FIDO2 cadastradas para o usuário."""
        keys = db.query(Fido2CredentialRecord).order_by(Fido2CredentialRecord.created_at.desc()).all()
        return [
            {
                "id": k.id,
                "device_name": k.device_name,
                "created_at": k.created_at.strftime("%d/%m/%Y %H:%M") if k.created_at else "-",
                "last_used_at": k.last_used_at.strftime("%d/%m/%Y %H:%M") if k.last_used_at else "Nunca",
                "sign_count": k.sign_count,
            }
            for k in keys
        ]

    def delete_fido2_key(self, key_id: str, db: Session) -> bool:
        """Exclui uma chave FIDO2 cadastrada."""
        rec = db.query(Fido2CredentialRecord).filter(Fido2CredentialRecord.id == key_id).first()
        if rec:
            db.delete(rec)
            db.commit()
            logger.info(f"Chave FIDO2 {key_id[:12]}... excluída.")
            return True
        return False


# Instância singleton para uso em toda a aplicação
security_service = SecurityService()
