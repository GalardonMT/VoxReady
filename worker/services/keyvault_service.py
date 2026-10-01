import os
import re
from typing import Optional, Dict
from utils.logger import get_logger

logger = get_logger("services.keyvault_service")

# Regex para referencias de Key Vault en App Settings de Azure
# Ejemplo: @Microsoft.KeyVault(SecretUri=https://myvault.vault.azure.net/secrets/mysecret/version)
KEYVAULT_URI_PATTERN = re.compile(r"@Microsoft\.KeyVault\(SecretUri=(?P<uri>[^)]+)\)", re.IGNORECASE)
KEYVAULT_VAULT_PATTERN = re.compile(
    r"@Microsoft\.KeyVault\(VaultName=(?P<vault>[^;]+);SecretName=(?P<secret>[^)]+)\)",
    re.IGNORECASE,
)


class KeyVaultService:
    """
    Servicio de resolución de secretos compatible con Azure Key Vault y fallback local.
    Permite resolver cadenas directas, referencias de App Service o consultar directamente
    el vault mediante Managed Identity.
    """

    def __init__(self, vault_url: Optional[str] = None):
        self.vault_url = vault_url or os.getenv("KEY_VAULT_URL")
        self._client = None
        self._cache: Dict[str, str] = {}

    def _get_client(self):
        if self._client is None and self.vault_url:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient

                credential = DefaultAzureCredential()
                self._client = SecretClient(vault_url=self.vault_url, credential=credential)
            except Exception as e:
                logger.warning(
                    f"No se pudo inicializar SecretClient para Key Vault ({self.vault_url}): {e}. "
                    "Se utilizarán variables de entorno como fallback."
                )
                self._client = False
        return self._client if self._client else None

    def resolve_value(self, value: Optional[str], default: Optional[str] = None) -> Optional[str]:
        """
        Si el valor es una referencia @Microsoft.KeyVault(...), extrae el secreto desde Azure.
        De lo contrario retorna el valor tal cual.
        """
        if not value:
            return default

        # Verificar si es una referencia @Microsoft.KeyVault(SecretUri=...)
        match_uri = KEYVAULT_URI_PATTERN.search(value)
        if match_uri:
            secret_uri = match_uri.group("uri").strip()
            return self.get_secret_by_uri(secret_uri, default=default)

        match_vault = KEYVAULT_VAULT_PATTERN.search(value)
        if match_vault:
            secret_name = match_vault.group("secret").strip()
            return self.get_secret(secret_name, default=default)

        return value

    def get_secret(self, secret_name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Obtiene un secreto por nombre. Primero revisa variables de entorno,
        luego la caché interna y finalmente consulta Key Vault si está configurado.
        """
        # Prioridad 1: Variable de entorno directa
        env_val = os.getenv(secret_name)
        if env_val and not env_val.startswith("@Microsoft.KeyVault"):
            return env_val

        # Prioridad 2: Si el valor en env es una referencia KeyVault, resolverla
        if env_val and env_val.startswith("@Microsoft.KeyVault"):
            resolved = self.resolve_value(env_val)
            if resolved:
                return resolved

        # Prioridad 3: Cache en memoria
        if secret_name in self._cache:
            return self._cache[secret_name]

        # Prioridad 4: SecretClient directo
        client = self._get_client()
        if client:
            try:
                secret = client.get_secret(secret_name)
                self._cache[secret_name] = secret.value
                return secret.value
            except Exception as e:
                logger.error(f"Error al obtener secreto '{secret_name}' de Key Vault: {e}")

        return default

    def get_secret_by_uri(self, secret_uri: str, default: Optional[str] = None) -> Optional[str]:
        """
        Resuelve un secreto directamente a partir de su URI completa en Azure Key Vault.
        """
        if secret_uri in self._cache:
            return self._cache[secret_uri]

        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            # Parsear vault_url y secret_name desde URI
            # Formato: https://<vault-name>.vault.azure.net/secrets/<secret-name>/[<version>]
            parts = secret_uri.split("/secrets/")
            vault_base_url = parts[0]
            subparts = parts[1].split("/")
            secret_name = subparts[0]
            version = subparts[1] if len(subparts) > 1 else None

            client = SecretClient(vault_url=vault_base_url, credential=DefaultAzureCredential())
            secret = client.get_secret(name=secret_name, version=version)
            self._cache[secret_uri] = secret.value
            return secret.value
        except Exception as e:
            logger.error(f"Error al resolver secreto desde URI '{secret_uri}': {e}")
            return default


# Instancia singleton para uso global
_kv_service = KeyVaultService()


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Helper global para obtener un secreto o variable de entorno resuelta."""
    raw_value = os.getenv(key)
    if raw_value:
        return _kv_service.resolve_value(raw_value, default=default)
    return _kv_service.get_secret(key, default=default)
