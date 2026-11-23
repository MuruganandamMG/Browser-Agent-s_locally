"""Concurrent BrowserOS tab actions with independent visual pointer overlays."""
import json
from urllib.parse import urlsplit

from neo_client import neo_browser

PARALLEL_TOOL = {'type': 'function', 'function': {
    'name': 'browser_parallel',
    'description': 'Run independent browser actions concurrently on 1 to 5 separate tabs. Each tab gets its own visible virtual agent pointer; the physical mouse is not moved. For new tabs provide url; for existing agent tabs provide page from a prior result. First open/read or snapshot, then use returned eN refs for click/fill. Actions in the same tab must stay sequential. Each result includes page, snapshot, timing and errors. Use this for simultaneous research or work across multiple tabs.',
    'parameters': {'type': 'object', 'properties': {'tasks': {'type': 'array', 'minItems': 1, 'maxItems': 5,
        'items': {'type': 'object', 'properties': {
            'url': {'type': 'string', 'description': 'HTTP/HTTPS URL to open in a NEW tab.'},
            'page': {'type': 'integer', 'description': 'Existing agent tab page ID; omit url when using page.'},
            'action': {'type': 'string', 'enum': ['read', 'snapshot', 'click', 'fill', 'press', 'scroll']},
            'ref': {'type': 'string', 'description': 'eN reference from latest snapshot, needed for click/fill.'},
            'value': {'type': 'string', 'description': 'Text for fill or key combination for press.'},
            'direction': {'type': 'string', 'enum': ['up', 'down', 'left', 'right']},
        }, 'required': ['action'], 'additionalProperties': False}}}, 'required': ['tasks'], 'additionalProperties': False},
}}

SCRIPT = r'''
const tasks = __TASKS__;
async function pointer(page, point, state) {
  return await page.evaluateInPage(({x,y,label,color}) => {
    let root = document.getElementById('__local_chat_agent_pointer');
    if (!root) {
      root = document.createElement('div');
      root.id = '__local_chat_agent_pointer';
      root.setAttribute('aria-hidden','true');
      root.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;transition:left 160ms ease-out,top 160ms ease-out;';
      const arrow = document.createElementNS('http://www.w3.org/2000/svg','svg');
      arrow.setAttribute('viewBox','0 0 24 28');
      arrow.style.cssText = 'width:24px;height:28px;display:block;filter:drop-shadow(0 1px 2px #0008)';
      const path = document.createElementNS('http://www.w3.org/2000/svg','path');
      path.setAttribute('d','M2 2 L2 23 L8 17 L13 26 L17 24 L12 15 L21 15 Z');
      path.setAttribute('stroke','white'); path.setAttribute('stroke-width','1.5');
      arrow.append(path); root.append(arrow);
      const badge = document.createElement('span');
      badge.style.cssText = 'display:block;margin-left:17px;padding:3px 8px;border-radius:6px;color:white;font:12px/1.5 sans-serif;white-space:nowrap;';
      root.append(badge); document.documentElement.append(root);
    }
    root.style.left = Math.max(0,Math.min(x,innerWidth-24))+'px';
    root.style.top = Math.max(0,Math.min(y,innerHeight-28))+'px';
    root.firstChild.firstChild.setAttribute('fill',color);
    root.lastChild.style.backgroundColor=color;
    root.lastChild.style.transform=x>innerWidth-160?'translateX(-100%)':'';
    root.lastChild.textContent=label;
    return true;
  }, {x:point.x,y:point.y,label:'Tab '+page.id+' · '+state,color:['#2563eb','#7c3aed','#047857','#b45309','#be185d'][page.id%5]});
}
return await Promise.all(tasks.map(async task => {
  const started=Date.now();
  let page, point={x:32,y:96}, cursor=false;
  try {
    page=task.url ? await browser.open(task.url) : browser.page(task.page);
    if (!task.url) {
      const own = (await browser.pages.list()).find(p=>p.pageId===page.id);
      if (!own || own.ownership!=='mine') throw new Error('Use a tab opened by this chat agent.');
    }
    if (task.ref) {
      const node=await page.resolveRef(task.ref);
      const box=await browser.cdp('DOM.getBoxModel',{backendNodeId:node.backendNodeId},node.sessionId);
      const q=box.model.content;
      point={x:(q[0]+q[2]+q[4]+q[6])/4,y:(q[1]+q[3]+q[5]+q[7])/4};
    }
    try { await pointer(page,point,'Working'); cursor=true; } catch {}
    if(task.action==='click') await page.click(task.ref);
    else if(task.action==='fill') await page.fill(task.ref,task.value);
    else if(task.action==='press') await page.press(task.value);
    else if(task.action==='scroll') await page.scroll(task.direction||'down',3);
    const snapshot=await page.snapshot({mode:'interactive'});
    snapshot.text=snapshot.text.slice(0,2200);
    snapshot.refs=snapshot.refs.slice(0,20);
    const text=task.action==='read' ? (await page.read()).slice(0,1200) : undefined;
    try { await pointer(page,point,'Done'); } catch { cursor=false; }
    return {page:page.id,started,finished:Date.now(),cursor,snapshot,text};
  } catch(error) {
    if(page) { try { await pointer(page,point,'Error'); } catch {} }
    return {page:page?.id,started,finished:Date.now(),error:String(error)};
  }
}));
'''


def parallel_browser(args):
    tasks = args.get('tasks')
    if set(args) != {'tasks'} or not isinstance(tasks, list) or not 1 <= len(tasks) <= 5:
        return {'error': 'Provide tasks: 1 to 5 independent tab actions.'}
    seen = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) - {'url','page','action','ref','value','direction'}:
            return {'error': 'Invalid tab task.'}
        if ('url' in task) == ('page' in task):
            return {'error': 'Each task needs either url or page, not both.'}
        if 'url' in task:
            try:
                parsed = urlsplit(task['url'])
                if parsed.scheme not in ('http','https') or not parsed.hostname: raise ValueError()
            except (ValueError, TypeError, AttributeError):
                return {'error': 'Use a full HTTP/HTTPS URL.'}
        elif type(task['page']) is not int or task['page'] < 0 or task['page'] in seen:
            return {'error': 'Existing page IDs must be distinct nonnegative integers.'}
        else:
            seen.add(task['page'])
        if task.get('action') not in ('read','snapshot','click','fill','press','scroll'):
            return {'error': 'Unsupported action.'}
        if task['action'] in ('click','fill') and (not isinstance(task.get('ref'), str) or not task['ref'].startswith('e') or not task['ref'][1:].isdigit()):
            return {'error': 'Click/fill needs an eN ref from the latest snapshot.'}
        if task['action'] in ('fill','press') and not isinstance(task.get('value'),str):
            return {'error': 'Fill/press needs a text value.'}
        if 'direction' in task and task['direction'] not in ('up','down','left','right'):
            return {'error': 'Invalid scroll direction.'}
    return neo_browser({'code': SCRIPT.replace('__TASKS__', json.dumps(tasks))}, max_chars=35000)
