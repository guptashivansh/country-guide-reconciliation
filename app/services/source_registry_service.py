class SourceRegistryService:
    def __init__(self, source_endpoint_repository):
        self.source_endpoint_repository = source_endpoint_repository

    def list_trusted_source_endpoints(self):
        return self.source_endpoint_repository.list_active_source_endpoints()
