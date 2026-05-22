from app.models.source_endpoint import SourceEndpoint


class TrustedSourceEndpointRepository:
    def list_active_source_endpoints(self):
        return [
            SourceEndpoint(
                country="India",
                authority="Wikipedia - Labour Law in India",
                url="https://en.wikipedia.org/wiki/Labour_law_in_India",
                sections=(
                    "annual_leave",
                    "working_hours",
                    "public_holidays",
                    "overtime",
                    "termination_notice",
                ),
            ),
            SourceEndpoint(
                country="India",
                authority="Wikipedia - Employees Provident Fund India",
                url="https://en.wikipedia.org/wiki/Employees%27_Provident_Fund_Organisation",
                sections=("provident_fund", "employee_benefits"),
            ),
        ]
