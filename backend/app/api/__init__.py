"""HTTP API (FastAPI) over the existing repositories + generation pipeline.

The Module 4 dashboard talks to this one service for both reads (applications,
listings, ranking) and actions (generate/steer/approve). It is a thin layer:
every endpoint delegates to the same repositories and ``generate_application``
pipeline the CLI uses, so behaviour stays identical across CLI and web.
"""
