# CLAUDE.md

## Project overview
This project is a Python web application that integrates with the F5 Distributed Cloud API documentation and API endpoints.
The goal is to build a maintainable, secure, and testable web app that can authenticate to F5 Distributed Cloud services, call relevant APIs, and present useful results through a web UI.

## Technical stack
- Language: Python 3.11+
- App type: web application
- Preferred backend framework: FastAPI unless the repository already standardizes on Flask or Django
- Frontend: server-rendered templates or a lightweight JS frontend, keep complexity low unless explicitly required
- HTTP client: `httpx`
- Data validation: `pydantic`
- Testing: `pytest`
- Lint/format: `ruff`

## External API context
The application integrates with F5 Distributed Cloud APIs.
Important reference documentation:
- Main docs: https://docs.cloud.f5.com/docs-v2/api
- API usage guide: https://docs.cloud.f5.com/docs-v2/platform/how-to/volt-automation/apis
- API reference entry point: https://docs.cloud.f5.com/docs-v2/reference/api-ref

Important API rules from the documentation:
- All API requests must be authenticated.
- Authentication methods supported are API Token or API Certificate.
- API token requests use the `Authorization: APIToken <token>` header.
- Most requests follow the format `https://<tenant>.console.ves.volterra.io/{service_prefix}/namespaces/{namespace}/{kind}`.
- Common service prefixes include `/api/config/`, `/api/data/`, `/api/web/`, `/api/waf/`, `/api/vk8s/`, `/api/secret_management/`, `/api/kms/`, and `/api/ml/data/`.

## Architecture rules
- Separate the code into clear layers:
  - `app/web/` for routes, views, request handlers
  - `app/services/` for business logic
  - `app/clients/` for F5 API client code
  - `app/models/` for request/response schemas
  - `tests/` for automated tests
- Keep all F5 API communication in a dedicated client module. Do not scatter raw HTTP calls across route handlers.
- Encapsulate tenant, namespace, service prefix, authentication, retries, and error handling in the client layer.
- Prefer typed models for API payloads and responses.
- Keep secrets out of source code.

## Security requirements
- Never hardcode API tokens, certificates, passwords, or tenant identifiers in the repository.
- Load secrets from environment variables or a secure secret store.
- Redact tokens and sensitive headers from logs.
- Validate and sanitize all user inputs before using them in API requests.
- Use timeouts for all outbound HTTP calls.
- Handle 401, 403, 404, 429, and 5xx responses explicitly.
- Follow least privilege for API credentials.
- If certificate auth is implemented, keep certificate paths configurable and never commit p12 files.

## Environment variables
Use environment variables with these default names unless the repo already defines a standard:
- `F5_XC_TENANT`
- `F5_XC_API_TOKEN`
- `F5_XC_API_CERT_PATH`
- `F5_XC_API_CERT_PASSWORD`
- `F5_XC_DEFAULT_NAMESPACE`
- `F5_XC_TIMEOUT_SECONDS`

## F5 API client conventions
- Build the base hostname as `https://{tenant}.console.ves.volterra.io`.
- Use API Token auth by default unless certificate auth is explicitly required.
- Centralize request construction in one reusable client.
- Always send explicit timeout values.
- Use structured exceptions for API failures.
- Add a helper for building URLs from `service_prefix`, `namespace`, `kind`, and optional object name.
- Start with read-only operations first, then add create/update/delete only when required.
- For mutating operations, require tests and clear validation of request payloads.

## Preferred implementation shape
Example modules:
- `app/clients/f5_xc_client.py`
- `app/services/f5_resources.py`
- `app/web/routes.py`
- `app/config.py`

Example client responsibilities:
- authentication headers
- base URL generation
- namespace-aware resource paths
- GET/POST/PUT/DELETE helpers
- response validation
- pagination or iteration helpers if needed

## Coding guidelines
- Prefer small functions with explicit inputs and outputs.
- Add type hints everywhere practical.
- Avoid large route handlers; move logic into services.
- Keep functions pure where possible.
- Write docstrings for client classes and public service methods.
- Preserve existing project conventions if they already exist in the repository.
- Do not introduce heavy frontend tooling unless the task clearly needs it.

## Error handling
- Convert F5 API errors into clear application-level exceptions.
- Provide safe user-facing messages in the web UI.
- Keep detailed diagnostics in server logs without exposing secrets.
- Distinguish authentication errors, authorization errors, validation errors, rate limiting, and upstream service failures.

## Testing requirements
Before finishing work, run the smallest relevant validation first, then broader checks if needed.

Preferred checks:
- `ruff check .`
- `pytest -q`

Testing expectations:
- Unit tests for the F5 client URL builder and auth header logic
- Unit tests for services using mocked F5 API responses
- Integration-style tests for web routes when practical
- Add regression tests for bug fixes

## Development workflow
When making changes:
1. Read the existing repository structure and follow its conventions.
2. Locate any existing config, HTTP client, or web framework setup before adding new files.
3. Implement the smallest change that satisfies the request.
4. Validate with targeted tests first.
5. Summarize assumptions, especially around tenant, namespace, and auth mode.

## Documentation expectations
When adding new integration code, document:
- required environment variables
- expected authentication mode
- which F5 service prefix is being used
- example resource path format
- any assumptions about namespace or tenant scope

## What to avoid
- Do not hardcode live tenant values.
- Do not embed API tokens in examples.
- Do not make unauthenticated assumptions about endpoints.
- Do not bypass the shared API client for one-off requests.
- Do not log raw request headers containing credentials.
- Do not add broad dependencies without a clear reason.

## Example request pattern
Use patterns consistent with the F5 docs:
- Base host: `https://<tenant>.console.ves.volterra.io`
- Header: `Authorization: APIToken <token>`
- Path shape: `/{service_prefix}/namespaces/{namespace}/{kind}`

Example: list objects in a namespace using a shared client abstraction rather than inline ad hoc requests.

## If the repository is empty
If starting from scratch, prefer this initial structure:
- `app/main.py`
- `app/config.py`
- `app/clients/f5_xc_client.py`
- `app/services/`
- `app/web/`
- `tests/`
- `pyproject.toml`
- `.env.example`

## Decision policy
If a request is ambiguous:
- prefer secure defaults
- prefer read-only API interactions over mutating ones
- ask for clarification before implementing destructive actions
- keep the design simple and production-friendly