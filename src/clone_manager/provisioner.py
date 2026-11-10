"""Docker provisioning and container replacement for generated clones."""
from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path

import docker


class DockerProvisioner:
    def __init__(self):
        self.client=docker.from_env()
        self.secret_root=Path(os.getenv("CLONE_SECRET_DIR","/var/lib/clone-manager/secrets"))
        self.database_url=os.environ["DATABASE_URL"]
        self.branding_url=os.getenv("BRANDING_IMAGE_URL","https://raw.githubusercontent.com/Portalsbot/image/main/photo_2026-11-01_20-42-48.jpg")
        self.file_image=os.getenv("FILE_SHARING_IMAGE","")
        self.link_image=os.getenv("LINK_SHARING_IMAGE","")
        self.network=os.getenv("CLONE_DOCKER_NETWORK") or None
        self.registry_user=os.getenv("GHCR_USERNAME")
        self.registry_token=os.getenv("GHCR_TOKEN")

    def _safe(self,clone_id):
        return re.sub(r"[^a-zA-Z0-9_.-]","-",clone_id)

    def _image(self,product,image_ref):
        image=image_ref or (self.file_image if product=="file" else self.link_image)
        if not image: raise RuntimeError(f"Image not configured for product: {product}")
        return image

    def _pull(self,image):
        if self.registry_user and self.registry_token:
            self.client.login(username=self.registry_user,password=self.registry_token,registry="ghcr.io")
        self.client.images.pull(image)

    def _config_file(self,clone_id,bot_token,owner_id,extra_environment):
        self.secret_root.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(self.secret_root,0o700)
        folder=self.secret_root/self._safe(clone_id)
        folder.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(folder,0o700)
        config={"BOT_TOKEN":bot_token,"DATABASE_URL":self.database_url,"CLONE_ID":clone_id,
                "OWNER_ID":str(owner_id),"BRANDING_IMAGE_URL":self.branding_url,"SMALL_CAPS":"true"}
        config.update(extra_environment or {})
        path=folder/f"config-{secrets.token_hex(8)}.json"
        path.write_text(json.dumps(config,ensure_ascii=False),encoding="utf-8"); os.chmod(path,0o600)
        return path

    def _run(self,image,product,clone_id,path,network,restart_policy):
        return self.client.containers.run(
            image,detach=True,name=f"tg-{self._safe(clone_id)}",
            environment={"CONFIG_FILE":"/run/secrets/app-config.json"},
            volumes={str(path):{"bind":"/run/secrets/app-config.json","mode":"ro"}},
            network=network if network is not None else self.network,
            restart_policy={"Name":restart_policy},
            labels={"app":"telegram-clone","clone_id":clone_id,"product":product},
        )

    def _create_sync(self,product,clone_id,token,owner_id,image_ref,network,restart_policy,extra_environment):
        image=self._image(product,image_ref); self._pull(image)
        path=self._config_file(clone_id,token,owner_id,extra_environment)
        try: return self._run(image,product,clone_id,path,network,restart_policy).id
        except Exception: path.unlink(missing_ok=True); raise

    async def create(self,product,clone_id,bot_token,owner_id,*,image_ref=None,network=None,
                     restart_policy="unless-stopped",extra_environment=None):
        import asyncio
        return await asyncio.to_thread(self._create_sync,product,clone_id,bot_token,owner_id,
                                       image_ref,network,restart_policy,extra_environment or {})

    def _redeploy_sync(self,product,clone_id,token,owner_id,current_id,image_ref,network,restart_policy,extra_environment):
        image=self._image(product,image_ref); self._pull(image)
        path=self._config_file(clone_id,token,owner_id,extra_environment)
        name=f"tg-{self._safe(clone_id)}"
        old=self.client.containers.get(current_id) if current_id else None
        backup=f"{name}-backup-{secrets.token_hex(3)}"
        new=None
        if old:
            old.stop(timeout=20); old.rename(backup)
        try:
            new=self._run(image,product,clone_id,path,network,restart_policy)
            new_id=new.id
            if old: old.remove(force=True)
            for stale in path.parent.glob("config-*.json"):
                if stale!=path: stale.unlink(missing_ok=True)
            return new_id
        except Exception:
            if new is not None:
                try: new.remove(force=True)
                except Exception: pass
            if old:
                try: old.rename(name); old.start()
                except Exception: pass
            path.unlink(missing_ok=True)
            raise

    async def redeploy(self,product,clone_id,bot_token,owner_id,*,current_container_id,
                       image_ref=None,network=None,restart_policy="unless-stopped",extra_environment=None):
        import asyncio
        return await asyncio.to_thread(self._redeploy_sync,product,clone_id,bot_token,owner_id,
                                       current_container_id,image_ref,network,restart_policy,extra_environment or {})

    async def stop(self,container_id):
        import asyncio
        await asyncio.to_thread(lambda:self.client.containers.get(container_id).stop(timeout=15))

    async def restart(self,container_id):
        import asyncio
        await asyncio.to_thread(lambda:self.client.containers.get(container_id).restart(timeout=15))

    async def status(self,container_id):
        import asyncio
        def inspect():
            try:
                container=self.client.containers.get(container_id); container.reload()
                state=(container.attrs.get("State") or {}).get("Status","unknown")
                return "running" if state=="running" else "stopped" if state in {"exited","created","dead"} else "unknown"
            except Exception: return "unknown"
        return await asyncio.to_thread(inspect)
