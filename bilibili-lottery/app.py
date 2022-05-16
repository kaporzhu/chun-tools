import json
import logging
import math
import random
import re
import zlib
from urllib.parse import urlparse

import click
import requests
from google.protobuf.json_format import MessageToJson
from ratelimiter import RateLimiter
from tenacity import retry, wait_exponential, stop_after_attempt
from tqdm import tqdm

import protos.dm_pb2 as Danmaku
from utils.crc32 import Cracker as CRC32Cracker


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)


UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36'

VIDEO_API = 'https://api.bilibili.com/x/web-interface/view'
DANMAKU_API = 'http://api.bilibili.com/x/v2/dm/web/seg.so'
COMMENT_API = 'https://api.bilibili.com/x/v2/reply/main'
COMMENT_REPLY_API = 'https://api.bilibili.com/x/v2/reply/reply'
USER_API = 'https://api.bilibili.com/x/space/acc/info'

# crc cracker - covert midhash to uid
crc32_cracker = CRC32Cracker()
logger = logging.getLogger('bilibili-lottery')


@retry(reraise=True, wait=wait_exponential(multiplier=1, max=10), stop=stop_after_attempt(3))
@RateLimiter(max_calls=1, period=1) # max 1 call per second
def perform_api_call(url, method, **kwargs):
    return requests.request(method, url, headers={'User-Agent': UA}, **kwargs)


def load_user_info(mid:str):
    resp = perform_api_call(USER_API, 'get', params={'mid': mid})
    return {
        'uname': resp.json()['data']['name']
    }


def load_video_info(video_url:str) -> dict:
    """
    format: https://www.bilibili.com/video/BV1Ea411J7Wc
    """
    video_id = re.search(r'/video/(\w+)', urlparse(video_url).path).group(1)
    resp = perform_api_call(VIDEO_API, 'get', params={'bvid': video_id})
    video_info = resp.json()['data']
    pages = [
        dict(id=page['cid'], duration=page['duration'])
        for page in video_info['pages']
    ]
    return {
        'title': video_info['title'],
        'pages': pages,
        'aid': video_info['aid'],
        'danmaku_count': video_info['stat']['danmaku'],
        'reply_count': video_info['stat']['reply']
    }


def load_danmakus(video_page_id:str, video_duration:int, total:int) -> list:
    danmakus = []
    # 6 mins/segment, 6000 max danmakus/segment
    segment_duration = 6 * 60
    pbar = tqdm(total=total, desc='加载弹幕')
    for i in range(math.ceil(video_duration / segment_duration)):
        params = {
            'type': 1,
            'oid': video_page_id,
            'segment_index': i + 1
        }
        pb_resp = perform_api_call(DANMAKU_API, 'get', params=params)
        dm_seg = Danmaku.DmSegMobileReply()
        dm_seg.ParseFromString(pb_resp.content)
        dm_json = json.loads(MessageToJson(dm_seg))
        for elem in dm_json['elems']:
            content = elem['content']
            logger.debug(f'Loaded danmaku: {content}')
            danmakus.append(dict(uidhash=elem['midHash'], content='DANMAKU - ' + content))
            pbar.update(1)

    pbar.update(pbar.total - pbar.n) # set pbar to 100%. some danmakus might be unavailable.
    pbar.close()
    return danmakus


def load_comments(video_aid:str, total:int) -> list:
    pbar = tqdm(total=total, desc='加载评论')
    comments = []
    comment_size = 20
    for i in range(math.ceil(total / comment_size)):
        params = {
            'jsonp': 'jsonp',
            'next': i + 1,
            'type': 1,
            'oid': video_aid,
            'mode': 3,
            'plat': 1
        }
        resp = perform_api_call(COMMENT_API, 'get', params=params)
        comments_json = resp.json()['data']['replies'] or []
        assert comment_size >= len(comments_json), 'Comment size no long enough'
        for comment in comments_json:
            comments.append(dict(
                uid=comment['member']['mid'],
                uname=comment['member']['uname'],
                content='COMMENT - ' + comment['content']['message']
            ))
            pbar.update(1)

            # load comment replies
            if comment['rcount'] > 0:
                if comment['rcount'] > len(comment['replies'] or []):
                    comments.extend(load_comment_replies(video_aid, comment['rpid'], comment['rcount']))
                else:
                    for reply in comment['replies'] or []:
                        comments.append(dict(
                            uid=reply['member']['mid'],
                            uname=reply['member']['uname'],
                            content='COMMENT - ' + reply['content']['message']
                        ))

    pbar.update(pbar.total - pbar.n) # set pbar to 100%. some replies might be unavailable.
    pbar.close()
    return comments


def load_comment_replies(video_aid:str, reply_id:str, total:int) -> list:
    params = {
        'jsonp': 'jsonp',
        'pn': 1,
        'type': 1,
        'oid': video_aid,
        'ps': total,
        'root': reply_id
    }
    resp = perform_api_call(COMMENT_REPLY_API, 'get', params=params)
    replies = []
    for reply in resp.json()['data']['replies'] or []:
        replies.append(dict(
            uid=reply['member']['mid'],
            uname=reply['member']['uname'],
            content='COMMENT - ' + reply['content']['message']
        ))
    return replies


@click.command()
@click.option('--video', prompt='视频链接')
@click.option('--lucky-count', prompt='中奖人数', type=int, default=1)
def run(video, lucky_count):
    video = load_video_info(video)
    logger.info(video['title'])

    # load danmakus
    all_danmakus = []
    for page in video['pages']:
        all_danmakus.extend(load_danmakus(page['id'], page['duration'], video['danmaku_count']))

    # load comments
    all_comments = load_comments(video['aid'], video['reply_count'])

    # combine users
    all_user_contents = {}
    for item in all_danmakus + all_comments:
        uidhash = item.get('uidhash') or format(zlib.crc32(item['uid'].encode('utf-8')), 'x')
        user_contents = all_user_contents.get(uidhash, {'uname': item.get('uname'), 'contents': []})
        user_contents['contents'].append(item['content'])
        all_user_contents[uidhash] = user_contents

    # lucky dog
    for _ in range(lucky_count):
        lucky_dog = random.choice(list(all_user_contents.keys()))
        uid = crc32_cracker.crack(lucky_dog)
        user_contents = all_user_contents[lucky_dog]
        uname = user_contents.get('uname') or load_user_info(uid)['uname']
        logger.info(f'{uname} https://space.bilibili.com/{uid} - {user_contents["contents"]}')


if __name__ == '__main__':
    run()
