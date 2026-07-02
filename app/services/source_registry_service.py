class SourceRegistryService:
    def __init__(self, source_endpoint_repository):
        self.source_endpoint_repository = source_endpoint_repository

    def list_trusted_source_endpoints(self):
        return self.source_endpoint_repository.list_active_source_endpoints()

    def list_endpoints_for_country(self, country_name):
        return self.source_endpoint_repository.list_endpoints_for_country(country_name)

    def list_countries(self):
        return self.source_endpoint_repository.list_countries()

    def active_country_names(self):
        """Canonical set of active country names — use to filter all country-scoped queries."""
        return {c["name"] for c in self.source_endpoint_repository.list_countries()}

    def list_authorities(self, country_id=None):
        return self.source_endpoint_repository.list_authorities(country_id)

    def get_registry_stats(self):
        return self.source_endpoint_repository.get_registry_stats()

    def verify_url(self, url):
        return self.source_endpoint_repository.verify_url(url)

    def classify_url(self, url, classification, **kwargs):
        return self.source_endpoint_repository.classify_url(url, classification, **kwargs)

    def list_classifications(self, limit=50):
        return self.source_endpoint_repository.list_classifications(limit)

    def create_country(self, data):
        return self.source_endpoint_repository.create_country(data)

    def update_country(self, country_id, data):
        return self.source_endpoint_repository.update_country(country_id, data)

    def delete_country(self, country_id):
        return self.source_endpoint_repository.delete_country(country_id)

    def create_authority(self, data):
        return self.source_endpoint_repository.create_authority(data)

    def update_authority(self, authority_id, data):
        return self.source_endpoint_repository.update_authority(authority_id, data)

    def delete_authority(self, authority_id):
        return self.source_endpoint_repository.delete_authority(authority_id)

    def create_endpoint(self, data):
        return self.source_endpoint_repository.create_endpoint(data)

    def update_endpoint(self, endpoint_id, data):
        return self.source_endpoint_repository.update_endpoint(endpoint_id, data)

    def delete_endpoint(self, endpoint_id):
        return self.source_endpoint_repository.delete_endpoint(endpoint_id)
