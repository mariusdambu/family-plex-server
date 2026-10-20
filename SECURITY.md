# Security and publication policy

Do not post real configuration, keys, tokens, appdata, backups, network inventories or private logs in issues. Describe the problem using fictional paths and accounts. Git history is public: deleting a secret from the latest file does not remove it from past commits. Revoke exposed credentials before doing history cleanup.

The dashboard is an administrative interface intended for a trusted administrator over an SSH tunnel. It executes privileged operations. Do not bind it to all interfaces or forward it from a router. Source validation is not a security certification.

The publication checker is a conservative artifact and known-pattern scan, not proof that arbitrary text contains no personal information. Review every new file before committing. The initial release is built from new generic sources, not copied private exports. No secret-dependent runtime configuration is committed.
