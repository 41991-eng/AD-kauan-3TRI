from flask import Blueprint
from controllers.download_controller import DownloadController

download_bp = Blueprint('download_bp', __name__)


@download_bp.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    return DownloadController.download_file(filename)