"""blogpub: notes + images -> polished Hexo post, previewed locally, published with one command."""

import warnings

# macOS's bundled Python is built against LibreSSL, which makes urllib3 print a harmless warning.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

__version__ = "0.1.0"
