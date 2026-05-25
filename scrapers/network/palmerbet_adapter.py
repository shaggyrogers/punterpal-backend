#!/usr/bin/env python3
"""
  PalmerbetAdapter.py
  ===================

  Description:           TODO
  Author:                Michael De Pasquale
  Creation Date:         2025-10-25
  Modification Date:     2025-11-21

"""

import ssl

import requests
import urllib3


class PalmerbetAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def init_poolmanager(
        self, connections: int, maxsize: int, block: bool, **pool_kwargs
    ) -> None:
        self.poolmanager = urllib3.PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            # Want TLSv1.3 / `TLS_AES_256_GCM_SHA384`
            ssl_context=urllib3.util.create_urllib3_context(
                # ciphers must conform to OpenSSL's cipher list format.
                # See https://docs.openssl.org/3.0/man1/openssl-ciphers/
                # Need to translate "TLS_AES_256_GCM_SHA384"...
                # Try SHA384+AESGCM
                # This doesn't work..? doesn't seem to know what this means
                # ciphers="SHA384+AESGCM",
                # Start with default, another problem to fix first...
                # Also - TLS_AES_256_GCM_SHA384 should be default? appears first in
                # SSLContext.get_cipers().
                ciphers="DEFAULT",
            ),
            **pool_kwargs
        )
