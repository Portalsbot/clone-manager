import pytest

from clone_manager.provisioner import RenderProvisioner


def make_provisioner(monkeypatch):
    monkeypatch.setenv("RENDER_API_KEY", "test-render-key")
    monkeypatch.setenv("RENDER_WORKSPACE_ID", "tea-test-workspace")
    monkeypatch.setenv("RENDER_REGISTRY_CREDENTIAL_ID", "rc_test_registry")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("OWNER_ID", "123456789")
    return RenderProvisioner()


def test_file_and_link_products_keep_their_repository_and_image_mapping(monkeypatch):
    provisioner = make_provisioner(monkeypatch)

    assert provisioner.repository_for("file") == "https://github.com/Portalsbot/File-Share-Bot"
    assert provisioner.image_for("file") == "ghcr.io/portalsbot/file-share-bot:latest"

    assert provisioner.repository_for("link") == "https://github.com/Portalsbot/link-sharing-bot"
    assert provisioner.image_for("link") == "ghcr.io/portalsbot/link-sharing-bot:latest"


def test_create_image_payload_uses_render_image_url_and_workspace(monkeypatch):
    provisioner = make_provisioner(monkeypatch)

    assert provisioner._image_configuration(
        "ghcr.io/portalsbot/file-share-bot:latest", include_owner=True
    ) == {
        "ownerId": "tea-test-workspace",
        "imagePath": "ghcr.io/portalsbot/file-share-bot:latest",
        "registryCredentialId": "rc_test_registry",
    }


def test_update_image_payload_uses_render_image_url_without_owner(monkeypatch):
    provisioner = make_provisioner(monkeypatch)

    assert provisioner._image_configuration(
        "ghcr.io/portalsbot/link-sharing-bot:latest", include_owner=False
    ) == {
        "imagePath": "ghcr.io/portalsbot/link-sharing-bot:latest",
        "registryCredentialId": "rc_test_registry",
    }


@pytest.mark.asyncio
async def test_create_file_worker_sends_render_background_worker_payload(monkeypatch):
    provisioner = make_provisioner(monkeypatch)
    captured = {}

    async def no_existing_service(name):
        return None

    async def fake_request(method, path, *, params=None, payload=None):
        captured.update(method=method, path=path, payload=payload)
        return {"service": {"id": "srv_file_test"}}

    monkeypatch.setattr(provisioner, "_find_service", no_existing_service)
    monkeypatch.setattr(provisioner, "_request", fake_request)

    service_id = await provisioner._create_service(
        "file",
        "file-123",
        "ghcr.io/portalsbot/file-share-bot:latest",
        [{"key": "BOT_TOKEN", "value": "telegram-test-token"}],
    )

    assert service_id == "srv_file_test"
    assert captured["method"] == "POST"
    assert captured["path"] == "/services"
    assert captured["payload"]["type"] == "background_worker"
    assert captured["payload"]["ownerId"] == "tea-test-workspace"
    assert captured["payload"]["image"] == {
        "ownerId": "tea-test-workspace",
        "imagePath": "ghcr.io/portalsbot/file-share-bot:latest",
        "registryCredentialId": "rc_test_registry",
    }
    assert captured["payload"]["serviceDetails"]["region"] == "singapore"
    assert captured["payload"]["serviceDetails"]["plan"] == "starter"


@pytest.mark.asyncio
async def test_existing_worker_update_uses_image_url_and_redeploys(monkeypatch):
    provisioner = make_provisioner(monkeypatch)
    requests = []

    async def existing_service(name):
        return "srv_link_existing"

    async def fake_request(method, path, *, params=None, payload=None):
        requests.append((method, path, payload))
        return None

    monkeypatch.setattr(provisioner, "_find_service", existing_service)
    monkeypatch.setattr(provisioner, "_request", fake_request)

    service_id = await provisioner._create_service(
        "link",
        "link-123",
        "ghcr.io/portalsbot/link-sharing-bot:latest",
        [{"key": "BOT_TOKEN", "value": "telegram-test-token"}],
    )

    assert service_id == "srv_link_existing"
    patch = next(item for item in requests if item[0] == "PATCH")
    assert patch[2]["image"] == {
        "imagePath": "ghcr.io/portalsbot/link-sharing-bot:latest",
        "registryCredentialId": "rc_test_registry",
    }
    assert not any("imageUrl" in str(item[2]) for item in requests)
    assert ("POST", "/services/srv_link_existing/deploys") in [
        (method, path) for method, path, _ in requests
    ]
