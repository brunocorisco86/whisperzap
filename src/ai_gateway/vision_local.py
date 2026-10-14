"""Motor de Visão Computacional Local 100% Zero-Token (YOLO11 Nano ONNX + Detector de Documentos).

Processa fotos e imagens recebidas via WhatsApp inteiramente na CPU local da VPS:
1. Detecta objetos físicos (veículos, caminhões de ração, pessoas, equipamentos) via YOLO11n ONNX.
2. Identifica notas fiscais e documentos impressos sem tentar extrair todo o texto ("É uma nota").
3. Retorna resultado estruturado para integração com PostgreSQL, Grafo NetworkX e ntfy.
4. Gasto de tokens: EXATAMENTE 0 TOKENS.
"""

import os
import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

import numpy as np
try:
    import pymupdf
except ImportError:
    pymupdf = None
import onnxruntime as ort

from src.config import settings

logger = logging.getLogger(__name__)

# Mapeamento selecionado das 80 classes do COCO Dataset para termos em Português
COCO_CLASSES_PT = {
    0: "Pessoa / Operador",
    1: "Bicicleta",
    2: "Carro / Veículo Leve",
    3: "Motocicleta",
    4: "Avião",
    5: "Ônibus",
    6: "Trem",
    7: "Caminhão / Transporte de Carga",
    8: "Barco",
    9: "Semáforo",
    14: "Pássaro / Ave",
    15: "Gato",
    16: "Cachorro",
    17: "Cavalo",
    18: "Ovelha",
    19: "Vaca / Bovino",
    20: "Elefante",
    21: "Urso",
    22: "Zebra",
    23: "Girafa",
    24: "Mochila",
    25: "Guarda-chuva",
    26: "Bolsa",
    28: "Mala de Viagem",
    39: "Garrafa",
    41: "Copo",
    42: "Garfo",
    43: "Faca",
    56: "Cadeira",
    57: "Sofá",
    58: "Planta / Vaso",
    59: "Cama",
    60: "Mesa de Jantar",
    62: "Televisão / Monitor",
    63: "Notebook / Laptop",
    64: "Mouse",
    65: "Controle Remoto",
    66: "Teclado",
    67: "Celular / Smartphone",
    72: "Geladeira",
    73: "Livro / Caderno",
    74: "Relógio",
}

# Classes com alta relevância operacional
OPERATIONAL_OBJECTS = {"Pessoa / Operador", "Carro / Veículo Leve", "Caminhão / Transporte de Carga", "Televisão / Monitor", "Notebook / Laptop", "Celular / Smartphone", "Livro / Caderno"}


@dataclass
class DetectedObject:
    """Objeto detectado pelo YOLO local."""
    label: str
    confidence: float
    box: List[float] = field(default_factory=list)  # [x1, y1, x2, y2] normalizados


@dataclass
class VisionResult:
    """Resultado estruturado da análise visual local."""
    summary: str
    is_document: bool
    detected_objects: List[DetectedObject] = field(default_factory=list)
    confidence: float = 0.0
    inference_time_ms: float = 0.0
    model_name: str = "yolo11n_onnx_local"
    tokens_consumed: int = 0


class VisionLocalEngine:
    """Motor de Visão Computacional Local com YOLO11n ONNX e Heurística de Documentos."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or os.path.join(settings.DATA_DIR, "models", "yolo11n.onnx")
        self.session: Optional[ort.InferenceSession] = None
        self._initialize_session()

    def _initialize_session(self) -> None:
        """Inicializa a sessão ONNX Runtime de forma thread-safe e de baixo consumo."""
        if not os.path.exists(self.model_path):
            logger.warning(f"⚠️ [VisionLocalEngine] Modelo não encontrado em {self.model_path}. Operando em modo heurístico.")
            return

        try:
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = 1
            opts.inter_op_num_threads = 1
            opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self.session = ort.InferenceSession(self.model_path, opts, providers=["CPUExecutionProvider"])
            logger.info(f"✅ [VisionLocalEngine] Modelo YOLO11n ONNX carregado com sucesso de {self.model_path}")
        except Exception as exc:
            logger.error(f"❌ [VisionLocalEngine] Falha ao carregar sessão ONNX: {exc}")
            self.session = None

    def _decode_image_to_rgb(self, image_bytes: bytes) -> Tuple[Optional[np.ndarray], int, int]:
        """Decodifica os bytes da imagem para array NumPy RGB (H, W, 3). Suporta PyMuPDF ou FFmpeg nativo."""
        # 1. Tenta via PyMuPDF se disponível
        try:
            import pymupdf
            doc = pymupdf.open(stream=image_bytes)
            page = doc[0]
            pix = page.get_pixmap()
            orig_w, orig_h = pix.width, pix.height
            samples = np.frombuffer(pix.samples, dtype=np.uint8)
            channels = 3 if not pix.alpha else 4
            img = samples.reshape((orig_h, orig_w, channels))[:, :, :3]
            doc.close()
            return img, orig_w, orig_h
        except Exception:
            pass

        # 2. Fallback universal via FFmpeg nativo (presente no container runner)
        try:
            import subprocess
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0",
                "-f", "image2pipe",
                "-vcodec", "rawvideo",
                "-pix_fmt", "rgb24",
                "pipe:1"
            ]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout_data, _ = proc.communicate(input=image_bytes, timeout=5.0)
            
            # Para obter as dimensões da imagem via ffprobe
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                "pipe:0"
            ]
            probe_proc = subprocess.Popen(probe_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            dim_str, _ = probe_proc.communicate(input=image_bytes, timeout=3.0)
            dim_parts = dim_str.decode().strip().split("x")
            
            if len(dim_parts) == 2:
                w, h = int(dim_parts[0]), int(dim_parts[1])
                img = np.frombuffer(stdout_data, dtype=np.uint8).reshape((h, w, 3))
                return img, w, h
        except Exception as ff_exc:
            logger.warning(f"⚠️ [VisionLocalEngine] Falha ao decodificar imagem via FFmpeg: {ff_exc}")

        return None, 0, 0

    def _preprocess_image(self, img: np.ndarray, orig_w: int, orig_h: int, target_size: int = 640) -> Optional[np.ndarray]:
        """Converte imagem RGB decodificada em tensor float32 normalizado (1, 3, 640, 640)."""
        try:
            # Redimensionamento simples e padding proporcional
            scale = min(target_size / orig_h, target_size / orig_w)
            new_h, new_w = max(1, int(orig_h * scale)), max(1, int(orig_w * scale))

            # Redimensiona via amostragem de pixels uniforme (ultra-rápido sem OpenCV/PIL)
            y_indices = np.linspace(0, orig_h - 1, new_h).astype(int)
            x_indices = np.linspace(0, orig_w - 1, new_w).astype(int)
            resized = img[y_indices[:, None], x_indices]

            # Cria canvas cinza (padding) de 640x640
            canvas = np.full((target_size, target_size, 3), 114, dtype=np.uint8)
            pad_top = (target_size - new_h) // 2
            pad_left = (target_size - new_w) // 2
            canvas[pad_top : pad_top + new_h, pad_left : pad_left + new_w] = resized

            # Normaliza para [0, 1] e altera layout para NCHW: (1, 3, 640, 640)
            tensor = canvas.astype(np.float32) / 255.0
            tensor = np.transpose(tensor, (2, 0, 1))
            tensor = np.expand_dims(tensor, axis=0)

            return tensor
        except Exception as exc:
            logger.warning(f"⚠️ [VisionLocalEngine] Erro ao processar tensor: {exc}")
            return None

    def _check_if_document_or_invoice(self, img: Optional[np.ndarray], w: int, h: int) -> Tuple[bool, float, str]:
        """Verifica deterministicamente se a imagem é um documento impresso ou nota fiscal."""
        if img is None or w == 0 or h == 0:
            return False, 0.0, ""

        try:
            # Aspect Ratio típico de folha de papel A4 ou cupom fiscal
            aspect = h / float(w) if w > 0 else 1.0
            is_paper_ratio = (1.20 <= aspect <= 1.70) or (aspect >= 1.90)  # A4, Carta ou Cupom fiscal longo

            # Análise de densidade de luminosidade média (documentos são fundos predominantemente claros)
            mean_brightness = float(np.mean(img))
            is_bright_paper = mean_brightness > 140.0  # Documento impresso em iluminação interna

            if is_paper_ratio and is_bright_paper:
                return True, 0.88, "É uma Nota Fiscal / Documento impresso"
            elif is_bright_paper and aspect > 1.15:
                return True, 0.75, "É um Documento ou Comprovante"
            return False, 0.0, ""
        except Exception:
            return False, 0.0, ""

    def classify_image(self, image_bytes: bytes, caption: Optional[str] = None) -> VisionResult:
        """Executa a análise visual de uma foto de ponta a ponta sem nenhum custo de tokens."""
        start_time = time.perf_counter()

        if not image_bytes or len(image_bytes) < 100:
            return VisionResult(
                summary="Imagem vazia ou corrompida.",
                is_document=False,
                confidence=0.0,
            )

        # 0. Decodificação única para otimização de latência
        img, orig_w, orig_h = self._decode_image_to_rgb(image_bytes)

        # 1. Checagem heurística local de Documento / Nota Fiscal
        is_doc, doc_conf, doc_label = self._check_if_document_or_invoice(img, orig_w, orig_h)

        # 2. Inferência com YOLO11 Nano em ONNX
        detected_objects: List[DetectedObject] = []
        if self.session is not None and img is not None:
            tensor = self._preprocess_image(img, orig_w, orig_h)
            if tensor is not None:
                try:
                    outputs = self.session.run(["output0"], {"images": tensor})
                    # Shape de saída do YOLO11: (1, 84, 8400) -> 4 box coords + 80 class probs
                    preds = outputs[0][0]  # Shape: (84, 8400)
                    scores_matrix = preds[4:, :]  # Shape: (80, 8400)

                    # Pega a classe com maior score para cada uma das 8400 âncoras
                    best_classes = np.argmax(scores_matrix, axis=0)
                    best_scores = np.max(scores_matrix, axis=0)

                    # Filtra detecções acima do threshold de confiança calibrado (0.28)
                    conf_threshold = 0.28
                    valid_mask = best_scores >= conf_threshold

                    seen_classes = set()
                    for idx in np.where(valid_mask)[0]:
                        class_id = int(best_classes[idx])
                        conf = float(best_scores[idx])
                        label = COCO_CLASSES_PT.get(class_id, f"Objeto #{class_id}")

                        if label not in seen_classes:
                            seen_classes.add(label)
                            detected_objects.append(
                                DetectedObject(
                                    label=label,
                                    confidence=round(conf, 2),
                                )
                            )
                except Exception as infer_err:
                    logger.error(f"❌ [VisionLocalEngine] Erro na inferência YOLO: {infer_err}")

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # 3. Consolidação do Resumo Visual em Português
        summary_parts = []
        if is_doc:
            summary_parts.append(doc_label)

        if detected_objects:
            obj_labels = [f"{o.label} ({int(o.confidence * 100)}%)" for o in detected_objects[:4]]
            summary_parts.append(f"Objetos identificados: {', '.join(obj_labels)}")

        if caption and caption.strip():
            summary_parts.append(f"Legenda do remetente: \"{caption.strip()}\"")

        if not summary_parts:
            summary_text = "Foto recebida (sem objetos proeminentes identificados localmente)."
        else:
            summary_text = " | ".join(summary_parts)

        best_conf = doc_conf if is_doc else (detected_objects[0].confidence if detected_objects else 0.5)

        logger.info(f"👁️ [VisionLocalEngine] Processado em {elapsed_ms:.1f}ms: '{summary_text}' (Tokens: 0)")

        return VisionResult(
            summary=summary_text,
            is_document=is_doc,
            detected_objects=detected_objects,
            confidence=round(best_conf, 2),
            inference_time_ms=round(elapsed_ms, 2),
            tokens_consumed=0,
        )


# Instância singleton para uso em todo o projeto
vision_local_engine = VisionLocalEngine()
