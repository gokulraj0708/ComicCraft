# Documentation Analysis and Engineering Decisions

## What the supplied document describes

The document specifies a FastAPI application that collects a story prompt, character, setting, tone, and art style; uses a fast Gemini model for a five-panel outline; uses a more capable Gemini model for narration and dialogue; generates one Stable Diffusion image per panel; builds a layout; and exports a PDF.

## Problems found in the partial design

1. **Brittle LLM parsing:** the snippets remove Markdown fences and split story text using `**Panel`. A small formatting change can break the application.
2. **Old model identifiers:** the document uses Gemini 1.5 names. Model names change, so this implementation makes both Gemini model IDs configurable.
3. **Incomplete source:** imports, configuration, schemas, error pages, static mounting, download handling, and full templates were missing.
4. **Inconsistent templates:** one deployment section mentions `result.html` and `all_users.html`, while the actual comic flow uses `comic_preview.html` and `export_success.html`.
5. **Character continuity:** independent image prompts can change the hero's appearance. This build creates a character bible and repeats it in each image prompt.
6. **No credential-free path:** the original design cannot be tested without paid/external services. This build includes a complete demo story provider and local placeholder art.
7. **Weak failure handling:** raw provider errors would fail the request. Optional story and image fallbacks are now explicit and reported in result metadata.
8. **Unsafe filenames/collisions:** prompt-based filenames and second-resolution timestamps can collide. This build uses UUID workspaces and fixed internal filenames.
9. **No structured persistence:** this build stores an atomic JSON manifest beside every comic and can reopen old previews by ID.
10. **No automated tests or deployment files:** pytest, Docker, editor settings, setup scripts, health checks, and cleanup tooling are included.

## Implemented architecture

```text
Browser / JSON client
        |
     FastAPI
        |
  ComicService orchestrator
   /       |          \
Story   Images        PDF
 |         |           |
Gemini  HF/local SD   fpdf2
or demo  or placeholder
        |
Filesystem repository (manifest, PNG panels, PDF)
```

## Reliability choices

- Pydantic schemas validate both user input and Gemini structured output.
- Panel counts and sequential panel numbers are checked explicitly.
- Provider keys remain in `.env`; generated output never contains secrets.
- Blocking SDK work runs in FastAPI's thread pool.
- Every output is isolated under `storage/comics/<uuid>/`.
- The requested and actual providers, fallback state, and warnings are returned to the client.
- The local Diffusers pipeline is optional and lazy-loaded because its dependencies and model weights are large.

## Scope

This is a complete single-server application suitable for learning, demonstrations, portfolios, and controlled internal use. Before public high-traffic deployment, add authentication, quotas/rate limiting, a persistent job queue, object storage, database indexing, content moderation tailored to your audience, observability, backups, and provider-specific cost controls.
