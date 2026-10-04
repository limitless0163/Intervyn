# DeepInterview Backend

The backend application lives in `app/` and follows the project architecture:
API routes under `app/api/routes`, request and wire models under
`app/schemas`, provider configuration under `app/core`, persistence contracts
under `app/repositories`, and interview workflows under `app/services`.

`app/schemas/shared_models.py` mirrors the TypeScript contracts in
`frontend/packages/shared/src` field-for-field. The parity checks in
`backend/tests/test_parity.py` compare them against the generated JSON Schemas
in `frontend/packages/shared/schema`.
