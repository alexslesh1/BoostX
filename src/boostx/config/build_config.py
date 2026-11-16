"""Values baked in when a release build is made (see packaging/). A source
checkout keeps these defaults."""

# Backend the app talks to when nothing else is configured. The Windows
# build workflow replaces None with the address of the test server.
DEFAULT_API_URL: str | None = None
