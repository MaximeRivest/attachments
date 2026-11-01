# Releasing attachments-dev (TypeScript)

## Every version: from GitHub, no login, no key

1. Set `version` in `ts/package.json`, add its section to
   `ts/CHANGELOG.md`, commit, push; `ci` must be green.
2. `gh release create ts-v<version> --title "attachments-dev <version>" --notes-file …`
   (`--prerelease` for `1.0.0-rc.1` and the like).
3. `.github/workflows/release-ts.yml` checks that the tag matches, runs the
   types, tests and build, and publishes with provenance through npm
   trusted publishing. A version with a `-` goes to the `next` tag.

Python's releases are separate: they use `v<version>` tags
(`publish-to-pypi.yml`); `ts-v…` tags never trigger them.

## Once: the first version and the trust

npm configures trusted publishing per package, and only for a package that
exists, so the first version is published by hand, then the trust is set.
Both need the account's two-factor key; npm skips the second check within
five minutes of the first, so it is one sitting:

```bash
cd ts && git status --short          # nothing
npm login --auth-type=web            # touch the key
npm publish --access public          # prepublishOnly: types, tests, build
npm trust github attachments-dev --repo MaximeRivest/attachments \
  --file release-ts.yml --env npm --allow-publish --yes
npm trust list attachments-dev
git tag ts-v0.1.0 && git push origin ts-v0.1.0
```
