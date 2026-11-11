from clone_manager.main import main
from clone_manager.provisioner import RenderProvisioner
from clone_manager.branding_config import IMAGE_URL
from clone_manager.fsubs import add_fsubs_handlers

def test_runtime_imports_and_branding():
    assert callable(main)
    assert callable(add_fsubs_handlers)
    assert RenderProvisioner is not None
    provisioner = RenderProvisioner.__new__(RenderProvisioner)
    assert provisioner.DEFAULT_IMAGES['file'] == 'ghcr.io/portalsbot/file-share-bot:latest'
    assert provisioner.DEFAULT_IMAGES['link'] == 'ghcr.io/portalsbot/link-sharing-bot:latest'
    assert provisioner.PRODUCT_REPOSITORIES['file'] == 'https://github.com/Portalsbot/File-Share-Bot'
    assert provisioner.PRODUCT_REPOSITORIES['link'] == 'https://github.com/Portalsbot/link-sharing-bot'
    assert IMAGE_URL == "https://i.ibb.co/PGpMYwYY/Gemini-Generated-Image-a7tjlia7tjlia7tj.png"
