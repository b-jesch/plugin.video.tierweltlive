"""Kodi Video Plugin for TIERWELT Live"""

import sys
import os
import re

import simplejson.errors
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import json
import xbmcvfs
import requests
from dateutil import parser
from urllib.parse import urlencode, parse_qsl
from xml.dom import minidom


HOST_AND_PATH = sys.argv[0]
ADDON_HANDLE = int(sys.argv[1])
dialog = xbmcgui.Dialog()
addon = xbmcaddon.Addon()
addon_id = addon.getAddonInfo('id')
addon_name = addon.getAddonInfo('name')
addon_version = addon.getAddonInfo('version')
addon_desc = addon.getAddonInfo('description')
addonPath = xbmcvfs.translatePath(addon.getAddonInfo('path')).encode('utf-8').decode('utf-8')
dataPath = xbmcvfs.translatePath(addon.getAddonInfo('profile')).encode('utf-8').decode('utf-8')
defaultFanart = os.path.join(addonPath, 'resources', 'fanart.jpg')
icon = os.path.join(addonPath, 'resources', 'icon.png')
KODI_ov20 = int(xbmc.getInfoLabel('System.BuildVersion')[0:2]) >= 20
BASE_URL = 'https://www.tierwelt-live.de/'


xbmcplugin.setContent(ADDON_HANDLE, 'videos')
xbmcplugin.addSortMethod(ADDON_HANDLE, xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE)


def get_userAgent(REV='109.0', VER='112.0'):
    base = 'Mozilla/5.0 {} Gecko/20100101 Firefox/'+VER
    if xbmc.getCondVisibility('System.Platform.Android'):
        if 'arm' in os.uname()[4]: return base.format('(X11; Linux arm64; rv:'+REV+')') # ARM based Linux
        return base.format('(X11; Linux x86_64; rv:'+REV+')') # x64 Linux
    elif xbmc.getCondVisibility('System.Platform.Windows'):
        return base.format('(Windows NT 10.0; Win64; x64; rv:'+REV+')') # Windows
    elif xbmc.getCondVisibility('System.Platform.IOS'):
        return 'Mozilla/5.0 (iPad; CPU OS 12_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0 Mobile/15E148 Safari/604.1' # iOS iPhone/iPad
    elif xbmc.getCondVisibility('System.Platform.Darwin') or xbmc.getCondVisibility('System.Platform.OSX'):
        return base.format('(Macintosh; Intel Mac OS X 10.15; rv:'+REV+')') # Mac OSX
    return base.format('(X11; Linux x86_64; rv:'+REV+')') # x64 Linux


def _header(REFERRER=None):
    header = {'Pragma': 'no-cache', 'Accept': '*/*', 'User-Agent': get_userAgent(), 'DNT': '1',
              'Upgrade-Insecure-Requests': '1', 'Accept-Encoding': 'gzip', 'Accept-Language': 'en-US,en;q=0.8,de;q=0.7'}
    if REFERRER:
        header['Referer'] = REFERRER
    return header


def getUrl(url, method='GET', REF=BASE_URL, headers=None, cookies=None, allow_redirects=True, verify=True, stream=None, data=None, json=None):
    simple = requests.Session()
    ANSWER = None
    try:
        response = simple.get(url, headers=_header(REF), allow_redirects=allow_redirects, verify=verify, stream=stream, timeout=30)
        ANSWER = response.json() if method in ['GET', 'POST'] else response.text
    except BaseException as e:
        xbmc.log(f"[{addon_id} v.{addon_version}] url: {url} === error: {str(e)}", xbmc.LOGERROR)
        dialog.notification(addon_name, 'No data received for this item!', xbmcgui.NOTIFICATION_ERROR)
        return sys.exit(0)
    return ANSWER


API_CONFIG = getUrl('https://twl-prod-static.s3.amazonaws.com/configs/projectConfig_smartclip.json')
API_VERSION = getUrl(API_CONFIG['ivms']['version'])['version_name']
VIDEO_API = API_CONFIG['ivms']['restapi'].replace('[version]', API_VERSION)
RSS_RESOURCE = getUrl('https://twl-aggregation.s3.us-east-1.amazonaws.com/livestream.xml', method='LOAD').encode('utf-8')


def build_url(**kwargs):
    """
    Create a URL for calling the plugin recursively from the given set of keyword arguments.
    """
    return '{}?{}'.format(HOST_AND_PATH, urlencode(kwargs))


def get_rss_content():
    """
    Read and convert RSS Feed of 'Tierwelt live' into JSON
    """
    xml = minidom.parseString(RSS_RESOURCE).getElementsByTagName('rss')
    channel = xml[0].getElementsByTagName('channel')
    items = channel[0].getElementsByTagName('item')
    rss_items = list()

    for item in items:
        DESC, RATED, AIRED = (None for _ in range(3))
        url = item.getElementsByTagName('media:content')[0].getAttribute('url')
        if item.getElementsByTagName('media:description')[0].firstChild is not None:
            DESC = item.getElementsByTagName('media:description')[0].firstChild.wholeText
        if item.getElementsByTagName('media:rating')[0].firstChild is not None:
            RATED = 'tv-' + item.getElementsByTagName('media:rating')[0].firstChild.wholeText
        if item.getElementsByTagName('pubDate')[0].firstChild is not None:
            AIRED = parser.parse(item.getElementsByTagName('pubDate')[0].firstChild.wholeText).strftime('%Y-%m-%d %H:%M:%S')
        video = dict({
            'title': item.getElementsByTagName('title')[0].firstChild.wholeText,
            'teaser': DESC,
            'images': item.getElementsByTagName('media:thumbnail')[0].getAttribute('url'),
            'crypto': re.compile('cdn.svmcdn4.com/hls/twl/(.+?)_hls720p.mp4/playlist.m3u8').findall(url)[0],
            'filesize': int(item.getElementsByTagName('media:content')[0].getAttribute('fileSize')),
            'mediatype': item.getElementsByTagName('media:content')[0].getAttribute('type'),
            'channels': int(item.getElementsByTagName('media:content')[0].getAttribute('channels')),
            'width': int(item.getElementsByTagName('media:content')[0].getAttribute('width')),
            'height': int(item.getElementsByTagName('media:content')[0].getAttribute('height')),
            'bitrate': int(item.getElementsByTagName('media:content')[0].getAttribute('bitrate')),
            'expression': item.getElementsByTagName('media:content')[0].getAttribute('expression'),
            'duration_in_secs': int(item.getElementsByTagName('media:content')[0].getAttribute('duration')),
            'language': item.getElementsByTagName('media:content')[0].getAttribute('lang'),
            'rating': RATED,
            'aired': AIRED
        })
        rss_items.append(video)
    return json.loads(json.dumps({'rss': rss_items}))


def list_pages():
    """
    Show plugin start page with pages "Aktuelle Livestreams, Themen, Kanäle, Tiere".
    https://d36olg7tmj6zg3.cloudfront.net/20230802110929/restapi/pages/home.json
    """
    xbmcplugin.setPluginCategory(ADDON_HANDLE, 'Start')
    topics = getUrl(f"{VIDEO_API}pages/home.json")['items']
    for topic in topics:
        topic_title = topic['unicode'].replace('Livestream', 'Aktuelle Livestreams')
        topic_id = topic['id']
        LTM = xbmcgui.ListItem(label=topic_title)
        if KODI_ov20:
            vinfo = LTM.getVideoInfoTag()
            vinfo.setTitle(topic_title)
            vinfo.setPlot(addon_desc)
        else:
            vinfo = {'Title': topic_title, 'Plot': addon_desc}
            LTM.setInfo(type='Video', infoLabels=vinfo)
        LTM.setArt({'thumb': icon, 'fanart': defaultFanart})
        if topic_title =='Aktuelle Livestreams':
            url = build_url(action='list_videos', id=None, category='rss')
        elif topic_title == 'Neueste Filme':
            url = build_url(action='list_videos', id=topic_id, category='movie')
        else:
            url = build_url(action='list_categories', page=topic_id, childs=False)
        xbmcplugin.addDirectoryItem(ADDON_HANDLE, url, LTM, True)
    xbmcplugin.endOfDirectory(ADDON_HANDLE)


def list_categories(page, childs):
    """
    Create the list of video categories in the Kodi interface.
    """
    xbmcplugin.setPluginCategory(ADDON_HANDLE, 'Kategorien')
    if childs == 'False':
        categories = getUrl(f"{VIDEO_API}containers/{page}.json")['items']
    else:
        categories = list(childs[1:-1].split(", "))
    for category in categories:
        if childs == 'False':
            category_module = category['module']
            category_id = category['id']
        else:
            category_module = "channel"
            category_id = category
        category_info = getUrl(f"{VIDEO_API}{category_module}s/{str(category_id)}.json")

        if childs == 'False':
            category_title = category['unicode']
        else:
            category_title = category_info['title']
        LTM = xbmcgui.ListItem(label=category_title)
        if KODI_ov20:
            vinfo = LTM.getVideoInfoTag()
            vinfo.setTitle(category_title)
            vinfo.setPlot(category_info.get('description', '') or category_info.get('teaser', '') or '...')
            if isinstance(category_info.get('tags', []), (list, tuple)): vinfo.setTags([str(category_info['tags'])])
            if category_info.get('web_airdate', ''): vinfo.setFirstAired(category_info['web_airdate'])
            vinfo.setStudios(['tierwelt-live.de'])
        else:
            vinfo = {'Title': category_title,
                     'Plot': (category_info.get('description', '') or category_info.get('teaser', '') or '...'),
                     'Tag': category_info.get('tags', '')}
            if category_info.get('web_airdate', ''): vinfo['Aired'] = category_info['web_airdate']
            vinfo['Studio'] = 'tierwelt-live.de'
            LTM.setInfo(type='Video', infoLabels=vinfo)
        LTM.setArt({
            'thumb': category_info['images'][0]['url'] if len(category_info.get('images', [])) > 0 else icon,
            'fanart': category_info['images'][0]['url'] if len(category_info.get('images', [])) > 0 else defaultFanart
        })
        url = build_url(action='list_videos', id=category_id, category=category_module)
        if 'child_channels' in category_info and len(category_info['child_channels']) > 0:
            url = build_url(action='list_categories', page=0, childs=category_info['child_channels'])
        xbmcplugin.addDirectoryItem(ADDON_HANDLE, url, LTM, True)
    xbmcplugin.endOfDirectory(ADDON_HANDLE)


def list_videos(page_id, page):
    """
    Create the list of playable videos in the Kodi interface.
    """
    xbmcplugin.setPluginCategory(ADDON_HANDLE, "Videos")
    if page == 'rss':
        category = get_rss_content()
    elif page == 'movie':
        category = getUrl(f"{VIDEO_API}containers/{page_id}.json")
    else:
        category = getUrl(f"{VIDEO_API}{page}s/{page_id}.json")

    if page == 'animal':
        category = getUrl(f"{VIDEO_API}containers/{str(category['containers'][0])}.json")
        videos = category['items']
    elif page == 'rss':
        videos = category['rss']
    elif page == 'movie':
        videos = category['items']
    else:
        videos = category['contains_media']

    for video in videos:
        if page in ['animal', 'movie']:
            media = getUrl(f"{VIDEO_API}media/{str(video['id'])}.json")
            crypto_idd = media['uuid'] if media.get('uuid', '') else 'None'
            full_title = f"{media['title']} - {media['subtitle']}" if media.get('subtitle', '') else media['title']
            LTM = xbmcgui.ListItem(label=full_title)
            if KODI_ov20:
                vinfo = LTM.getVideoInfoTag()
                vinfo.setTitle(full_title)
                vinfo.setPlot(media.get('description', '') or media.get('teaser', '') or '...')
                vinfo.setDuration(int(round(media.get('duration_in_ms', 0)/1000)))
                if isinstance(media.get('tags', []), (list, tuple)): vinfo.setTags([str(media['tags'])])
                if media.get('web_airdate', ''): vinfo.setFirstAired(media['web_airdate'])
                vinfo.setStudios(['tierwelt-live.de'])
                vinfo.setMediaType('video')
            else:
                vinfo = {'Title': full_title,
                         'Plot': (media.get('description', '') or media.get('teaser', '') or '...'),
                         'Duration': int(round(media.get('duration_in_ms', 0) / 1000)), 'Tag': media.get('tags', '')}
                if media.get('web_airdate', ''): vinfo['Aired'] = media['web_airdate']
                vinfo['Studio'] = 'tierwelt-live.de'
                vinfo['Mediatype'] = 'video'
                LTM.setInfo(type='Video', infoLabels=vinfo)
            LTM.setArt({
                'thumb': media['images'][0]['url'] if len(media.get('images', [])) > 0 else icon,
                'fanart': media['images'][0]['url'] if len(media.get('images', [])) > 0 else defaultFanart
            })
            url = build_url(action='play_video', id=video['id'], uuid=crypto_idd)
        elif page == 'rss':
            LTM = xbmcgui.ListItem(label=video['title'])
            if KODI_ov20:
                vinfo = LTM.getVideoInfoTag()
                vinfo.setTitle(video['title'])
                vinfo.setPlot(video.get('teaser', '') or '...')
                vinfo.setDuration(int(video.get('duration_in_secs', 0)))
                vinfo.setMpaa(video.get('rating', '') or "")
                if video.get('aired', ''): vinfo.setFirstAired(video['aired'])
                vinfo.setStudios(['tierwelt-live.de'])
                vinfo.setMediaType('video')
            else:
                vinfo = {'Title': video['title'], 'Plot': (video.get('teaser', '') or '...'),
                         'Duration': int(video.get('duration_in_secs', 0)), 'Mpaa': (video.get('rating', '') or "")}
                if video.get('aired', ''): vinfo['Aired'] = video['aired']
                vinfo['Studio'] = 'tierwelt-live.de'
                vinfo['Mediatype'] = 'video'
                LTM.setInfo(type='Video', infoLabels=vinfo)
            LTM.setArt({'thumb': video['images'], 'fanart': video['images']})
            url = build_url(action='play_video', id=video['crypto'], uuid=video['crypto'])
        else:
            full_title = f"{video['title']} - {video['subtitle']}" if video.get('subtitle', '') else video['title']
            LTM = xbmcgui.ListItem(label=full_title)
            if KODI_ov20:
                vinfo = LTM.getVideoInfoTag()
                vinfo.setTitle(full_title)
                vinfo.setPlot(video.get('description', '') or video.get('teaser', '') or '...')
                vinfo.setDuration(int(round(video.get('duration_in_ms', 0)/1000)))
                if isinstance(category.get('tags', []), (list, tuple)): vinfo.setTags([str(category['tags'])])
                if category.get('web_airdate', ''): vinfo.setFirstAired(category['web_airdate'])
                vinfo.setStudios(['tierwelt-live.de'])
                vinfo.setMediaType('video')
            else:
                vinfo = {'Title': full_title,
                         'Plot': (video.get('description', '') or video.get('teaser', '') or '...'),
                         'Duration': int(round(video.get('duration_in_ms', 0) / 1000)), 'Tag': category.get('tags', '')}
                if category.get('web_airdate', ''): vinfo['Aired'] = category['web_airdate']
                vinfo['Studio'] = 'tierwelt-live.de'
                vinfo['Mediatype'] = 'video'
                LTM.setInfo(type='Video', infoLabels=vinfo)
            LTM.setArt({
                'thumb': video['images'][0]['url'] if len(video.get('images', [])) > 0 else icon,
                'fanart': video['images'][0]['url'] if len(video.get('images', [])) > 0 else defaultFanart
            })
            url = build_url(action='play_video', id=video['pk'], uuid='None')
        LTM.setProperty('IsPlayable', 'true')
        xbmcplugin.addDirectoryItem(ADDON_HANDLE, url, LTM, False)
    xbmcplugin.endOfDirectory(ADDON_HANDLE)


def play_video(video_id, uuid):
    """
    Play a video by the provided path.
    """
    if uuid == 'None':
        uuid = getUrl(f"{VIDEO_API}media/{video_id}.json")['uuid']
    play_item = xbmcgui.ListItem(path = f"https://cdn-segments.tierwelt-live.de/{uuid}_twl_720p.m4v/playlist.m3u8")
    xbmcplugin.setResolvedUrl(ADDON_HANDLE, True, play_item)


def router(paramstring):
    """
    Router function that calls other functions depending on the provided paramstring
    """
    params = dict(parse_qsl(paramstring))
    if params:
        if params['action'] == 'list_categories':
            list_categories(params['page'], params['childs'])
        elif params['action'] == 'list_videos':
            list_videos(params['id'], params['category'])
        elif params['action'] == 'play_video':
            play_video(params['id'], params['uuid'])
        else:
            raise ValueError(f"Invalid paramstring: {paramstring} !!!")
    else:
        list_pages()


if __name__ == '__main__':
    router(sys.argv[2][1:])
