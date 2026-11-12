import logging
from flask import jsonify, redirect, send_from_directory
from werkzeug.exceptions import NotFound

from models.download_model import DownloadModel
from controllers.upload_controller import S3_BUCKET, PASTA_UPLOAD_LOCAL, get_s3

logger = logging.getLogger("download")

EXPIRA_EM_SEGUNDOS = 300  # a URL de download vale 5 minutos


class DownloadController:

    @staticmethod
    def download_file(filename):
        """Valida o nome no banco e entrega o arquivo (S3 em produção, disco local em dev)."""
        registro = DownloadModel.find_by_filename(filename)
        if not registro:
            logger.warning(f"Download falhou: {filename} não existe no banco")
            return jsonify({"erro": "Arquivo não encontrado"}), 404

        if S3_BUCKET:
            return DownloadController._baixar_do_s3(registro)
        return DownloadController._baixar_local(registro)

    @staticmethod
    def _baixar_do_s3(registro):
        from botocore.exceptions import ClientError

        chave = registro["filepath"]
        # Nome que o usuário vai ver ao baixar: tira o prefixo do UUID
        nome_original = registro["filename"].split("_", 1)[-1]

        try:
            s3 = get_s3()
            s3.head_object(Bucket=S3_BUCKET, Key=chave)  # confirma que o objeto existe
            url = s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": S3_BUCKET,
                    "Key": chave,
                    "ResponseContentDisposition": f'attachment; filename="{nome_original}"',
                },
                ExpiresIn=EXPIRA_EM_SEGUNDOS,
            )
        except ClientError as e:
            codigo = e.response.get("Error", {}).get("Code")
            if codigo in ("404", "NoSuchKey", "NotFound"):
                logger.warning(f"Download falhou: {chave} está no banco mas não no storage")
                return jsonify({"erro": "Arquivo não encontrado"}), 404
            logger.exception(f"Erro no storage ao baixar {chave}")
            return jsonify({"erro": "Erro interno ao baixar o arquivo"}), 500
        except Exception:
            logger.exception(f"Erro ao gerar URL de download de {chave}")
            return jsonify({"erro": "Erro interno ao baixar o arquivo"}), 500

        logger.info(f"Download liberado: {registro['filename']}")
        return redirect(url, code=302)

    @staticmethod
    def _baixar_local(registro):
        """Modo desenvolvimento (sem S3): lê do disco local."""
        try:
            return send_from_directory(
                PASTA_UPLOAD_LOCAL, registro["filename"], as_attachment=True
            )
        except NotFound:
            logger.warning(f"Download falhou: {registro['filename']} não está no disco")
            return jsonify({"erro": "Arquivo não encontrado"}), 404