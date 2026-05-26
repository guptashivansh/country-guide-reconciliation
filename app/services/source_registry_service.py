class SourceRegistryService:
    def __init__(self, source_endpoint_repository):
        self.source_endpoint_repository = source_endpoint_repository

    def list_trusted_source_endpoints(self):
        return self.source_endpoint_repository.list_active_source_endpoints()

    def list_endpoints_for_country(self, country_name):
        return self.source_endpoint_repository.list_endpoints_for_country(country_name)

    def list_countries(self):
        return self.source_endpoint_repository.list_countries()

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

    def create_endpoint(self, data):
        return self.source_endpoint_repository.create_endpoint(data)
