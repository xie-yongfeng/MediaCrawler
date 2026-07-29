# Third-party notice

The Fund Insight Desk Douyin collector uses the MediaCrawler technical path
for signed active web requests. The following components are copied or adapted
from that path:

- `douyin.js` is copied from `MediaCrawler/libs/douyin.js` for request signing.
- `../signer.py` adapts MediaCrawler's `get_a_bogus` invocation.
- `../client.py` adapts the creator profile, creator post list, and aweme detail
  request flow from `media_platform/douyin/client.py`.

- Source: https://github.com/NanmiCoder/MediaCrawler
- Copyright: MediaCrawler contributors
- License: NON-COMMERCIAL LEARNING LICENSE 1.1

The complete license text is distributed at
`LICENSES/MediaCrawler-NON-COMMERCIAL-LEARNING-LICENSE-1.1.txt`. These copied
and adapted components retain that license and must not be used commercially
without permission from the copyright holder.
