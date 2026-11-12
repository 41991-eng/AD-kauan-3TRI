import os
from flask import Flask, jsonify
from werkzeug.exceptions import RequestEntityTooLarge
from database.db import init_db
from routes.upload_route import upload_bp
from routes.download_route import download_bp

app = Flask(__name__)

# Só usado em desenvolvimento (sem S3). Em produção os arquivos vão pro storage externo.
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_DIR', 'uploads')

# Teto geral da requisição (o limite de 30 KB do arquivo é validado no controller)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024  # 1 MB

# Cria a tabela se não existir. Se DATABASE_URL faltar, o deploy falha aqui e o erro aparece nos logs.
init_db()

app.register_blueprint(upload_bp, url_prefix='/uploads')
app.register_blueprint(download_bp, url_prefix='/downloads')


@app.route('/health')
def health():
    """Rota simples pro Render saber que o serviço subiu."""
    return jsonify({"status": "ok"}), 200


@app.errorhandler(RequestEntityTooLarge)
def requisicao_grande(e):
    return jsonify({"erro": "Requisição grande demais"}), 413


if __name__ == '__main__':
    # Só pra rodar local: FLASK_DEBUG=1 liga o debug; em produção quem sobe é o gunicorn
    app.run(
        debug=os.getenv('FLASK_DEBUG') == '1',
        port=int(os.getenv('PORT', 5000)),
    )