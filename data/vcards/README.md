# Diretório de Importação de vCards (Google Contacts / Apple / Android)

Coloque aqui o seu arquivo `.vcf` exportado do [Google Contacts](https://contacts.google.com) ou do seu smartphone.

### Arquivo sugerido:
- `data/vcards/contacts.vcf` (ou qualquer arquivo com extensão `.vcf` ou `.vcard`)

### Como importar após salvar o arquivo:
Execute o comando no terminal do projeto:
```bash
python3 scripts/import_vcard.py
```
Ou se estiver rodando via Docker:
```bash
docker exec -it whisperzap-api python scripts/import_vcard.py
```
O script fará o parsing de todos os contatos, normalizará os telefones com DDD/DDI e cadastrará no Banco de Dados e Grafo de Conhecimento com a role `UNKNOWN`.
