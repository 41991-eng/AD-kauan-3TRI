import os
import sys
import uuid
import logging
import mimetypes
from flask import jsonify, request
from werkzeug.utils import secure_filename

from models.upload_model import UploadModel

# Logs vão pro stdout: no Render aparecem na aba "Logs" (arquivo local some a cada deploy)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("upload")

# Configuração de upload
EXTENSOES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt'}
TAMANHO_MAXIMO_ARQUIVO = 30 * 1024  # 30 KB
TAMANHO_LEGIVEL = f"{TAMANHO_MAXIMO_ARQUIVO // 1024} KB"

# Assinaturas (magic bytes) pra confirmar que o conteúdo bate com a extensão
ASSINATURAS = {
    'png': (b'\x89PNG\r\n\x1a\n',),
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'gif': (b'GIF87a', b'GIF89a'),
    'pdf': (b'%PDF-',),
}

# Storage: S3 (ou compatível) em produção, disco local só pra desenvolvimento
S3_BUCKET = os.getenv("S3_BUCKET")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")  # opcional (R2, Supabase, etc.)
S3_REGION = os.getenv("S3_REGION", "us-east-1")
PASTA_UPLOAD_LOCAL = os.getenv("UPLOAD_DIR", "uploads")

_s3_client = None


def get_s3():
    """Cria o cliente S3 uma vez só. Credenciais vêm de AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY."""
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client("s3", endpoint_url=S3_ENDPOINT_URL, region_name=S3_REGION)
    return _s3_client


def _ip_cliente():
    """Atrás do proxy do Render, remote_addr é o IP do proxy; o real vem no X-Forwarded-For."""
    encaminhado = request.headers.get("X-Forwarded-For", "")
    return encaminhado.split(",")[0].strip() or request.remote_addr


class UploadController:

    @staticmethod
    def extensao(nome_arquivo):
        """Devolve a extensão em minúsculas (ou '' se não tiver)."""
        if '.' not in nome_arquivo:
            return ''
        return nome_arquivo.rsplit('.', 1)[1].lower()

    @staticmethod
    def arquivo_permitido(nome_arquivo):
        """Verifica se a extensão do arquivo é permitida."""
        return UploadController.extensao(nome_arquivo) in EXTENSOES_PERMITIDAS

    @staticmethod
    def tamanho_arquivo(arquivo):
        """Mede o tamanho real do arquivo, sem depender do header Content-Length."""
        arquivo.stream.seek(0, os.SEEK_END)
        tamanho = arquivo.stream.tell()
        arquivo.stream.seek(0)
        return tamanho

    @staticmethod
    def conteudo_confere(arquivo, extensao):
        """Confere se o conteúdo real bate com a extensão declarada."""
        arquivo.stream.seek(0)
        try:
            if extensao == 'txt':
                arquivo.stream.read().decode('utf-8')
                return True
            inicio = arquivo.stream.read(8)
            return any(inicio.startswith(a) for a in ASSINATURAS.get(extensao, ()))
        except UnicodeDecodeError:
            return False
        finally:
            arquivo.stream.seek(0)

    @staticmethod
    def salvar(arquivo, nome_arquivo):
        """Salva no S3 se configurado; senão, no disco local (dev). Devolve a chave/caminho salvo."""
        if S3_BUCKET:
            chave = f"uploads/{nome_arquivo}"
            tipo = mimetypes.guess_type(nome_arquivo)[0] or "application/octet-stream"
            get_s3().upload_fileobj(
                arquivo.stream,
                S3_BUCKET,
                chave,
                ExtraArgs={"ContentType": tipo},
            )
            return chave

        os.makedirs(PASTA_UPLOAD_LOCAL, exist_ok=True)
        caminho = os.path.join(PASTA_UPLOAD_LOCAL, nome_arquivo)
        arquivo.save(caminho)
        return caminho

    @staticmethod
    def upload_file():
        """Recebe e processa o upload do arquivo."""

        # Verifica se um arquivo foi enviado
        if 'file' not in request.files:
            logger.warning("Falha no upload: nenhum arquivo enviado")
            return jsonify({"erro": "Nenhum arquivo enviado"}), 400

        arquivo = request.files['file']

        # Verifica se o nome do arquivo está vazio
        if arquivo.filename == '':
            logger.warning("Falha no upload: nome do arquivo vazio")
            return jsonify({"erro": "Nome do arquivo vazio"}), 400

        # Verifica a extensão (descarta rápido o que nem é permitido)
        if not UploadController.arquivo_permitido(arquivo.filename):
            logger.warning(f"Falha no upload: {arquivo.filename} - tipo não permitido")
            return jsonify({
                "erro": "Tipo de arquivo não permitido!",
                "tipos_permitidos": sorted(EXTENSOES_PERMITIDAS)
            }), 400

        # Limpa o nome e valida de novo (secure_filename pode deixar o nome sem extensão)
        nome_limpo = secure_filename(arquivo.filename)
        extensao = UploadController.extensao(nome_limpo)
        if extensao not in EXTENSOES_PERMITIDAS:
            logger.warning(f"Falha no upload: nome inválido após limpeza ({arquivo.filename})")
            return jsonify({"erro": "Nome de arquivo inválido"}), 400

        # Verifica o tamanho real do arquivo
        if UploadController.tamanho_arquivo(arquivo) > TAMANHO_MAXIMO_ARQUIVO:
            logger.warning(f"Falha no upload: {arquivo.filename} - excede {TAMANHO_LEGIVEL}")
            return jsonify({
                "erro": f"Arquivo excede o tamanho máximo permitido ({TAMANHO_LEGIVEL})"
            }), 413

        # Confere se o conteúdo bate com a extensão
        if not UploadController.conteudo_confere(arquivo, extensao):
            logger.warning(f"Falha no upload: {arquivo.filename} - conteúdo não confere com a extensão")
            return jsonify({"erro": "O conteúdo do arquivo não corresponde ao tipo informado"}), 400

        # Nome único pra ninguém sobrescrever o arquivo de ninguém
        nome_arquivo = f"{uuid.uuid4().hex}_{nome_limpo}"

        try:
            filepath = UploadController.salvar(arquivo, nome_arquivo)
            if not UploadModel.save_file(nome_arquivo, filepath):
                logger.error(f"Falha no upload: {nome_arquivo} - nome duplicado no banco")
                return jsonify({"erro": "Conflito ao registrar o arquivo"}), 409
        except Exception:
            logger.exception(f"Erro ao salvar {nome_arquivo}")
            return jsonify({"erro": "Erro interno ao salvar o arquivo"}), 500

        logger.info(f"Upload bem-sucedido: {nome_arquivo} | IP: {_ip_cliente()}")

        return jsonify({
            "mensagem": "Arquivo salvo com sucesso!",
            "arquivo": nome_arquivo
        }), 200