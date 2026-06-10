# site/ — superseded

The production website (attachments.dev) now lives in its own repo:
`~/Projects/attachments-web` (landing, docs, DSL reference, playground,
pricing). Deploy with that repo's `deploy.sh`, which rsyncs to
`/opt/attachments/site/` on the attachments-api EC2 instance.

The `index.html` here is the launch-era single page, kept for history.
Do NOT rsync this directory to the server — it would clobber the real
site. The nginx mount and CORS config remain in `deploy/nginx.conf`.
