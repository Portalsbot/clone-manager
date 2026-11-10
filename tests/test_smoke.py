from clone_manager.main import main
from clone_manager.provisioner import DockerProvisioner
from clone_manager.branding_config import IMAGE_URL
from clone_manager.fsubs import add_fsubs_handlers

def test_runtime_imports_and_branding():
    assert callable(main)
    assert callable(add_fsubs_handlers)
    assert DockerProvisioner is not None
    assert IMAGE_URL == "https://i.ibb.co/PGpMYwYY/Gemini-Generated-Image-a7tjlia7tjlia7tj.png"
