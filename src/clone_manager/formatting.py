"""Safe small-caps and custom Telegram HTML markup renderer."""
from __future__ import annotations
import html,re
from urllib.parse import urlparse
SMALL_CAPS=str.maketrans({"a":"ᴀ","b":"ʙ","c":"ᴄ","d":"ᴅ","e":"ᴇ","f":"ꜰ","g":"ɢ","h":"ʜ","i":"ɪ","j":"ᴊ","k":"ᴋ","l":"ʟ","m":"ᴍ","n":"ɴ","o":"ᴏ","p":"ᴘ","q":"ǫ","r":"ʀ","s":"ѕ","t":"ᴛ","u":"ᴜ","v":"ᴠ","w":"ᴡ","x":"x","y":"ʏ","z":"ᴢ","A":"ᴀ","B":"ʙ","C":"ᴄ","D":"ᴅ","E":"ᴇ","F":"ꜰ","G":"ɢ","H":"ʜ","I":"ɪ","J":"ᴊ","K":"ᴋ","L":"ʟ","M":"ᴍ","N":"ɴ","O":"ᴏ","P":"ᴘ","Q":"ǫ","R":"ʀ","S":"ѕ","T":"ᴛ","U":"ᴜ","V":"ᴠ","W":"ᴡ","X":"x","Y":"ʏ","Z":"ᴢ"})
TOKEN=re.compile(r'\((?P<close>/)?(?P<tag>B|I|U|S|CODE|PRE|Q|SPOILER|LINK)(?:\s+url="(?P<url>[^"]+)")?\)',re.I)
TAG_MAP={"B":"b","I":"i","U":"u","S":"s","CODE":"code","PRE":"pre","Q":"blockquote","SPOILER":"tg-spoiler"}
QUOTE_ENABLED = True

def set_quote_enabled(enabled: bool):
    global QUOTE_ENABLED
    QUOTE_ENABLED = bool(enabled)

def render_text(source:str,small_caps:bool=True)->str:
    source="" if source is None else str(source)
    if QUOTE_ENABLED:
        source=re.sub(r"\(Quote start\)", "(Q)", source, flags=re.I)
        source=re.sub(r"\(Quote end\)", "(/Q)", source, flags=re.I)
    source=re.sub(r"\*\*(.+?)\*\*",r"(B)\1(/B)",source,flags=re.S)
    source=re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)",r"(I)\1(/I)",source)
    source=re.sub(r"`([^`\n]+)`",r"(CODE)\1(/CODE)",source)
    out=[]; stack=[]; pos=0
    for match in TOKEN.finditer(source):
        segment=source[pos:match.start()]
        in_code=any(tag in {"CODE","PRE"} for tag,_ in stack)
        out.append(html.escape(segment.translate(SMALL_CAPS) if small_caps and not in_code else segment))
        tag=match.group("tag").upper(); closing=bool(match.group("close"))
        if tag=="LINK":
            if closing and stack and stack[-1][0]=="LINK": out.append("</a>"); stack.pop()
            elif not closing:
                url=match.group("url") or ""; parsed=urlparse(url)
                if parsed.scheme in {"http","https"} and parsed.netloc:
                    out.append(f'<a href="{html.escape(url,quote=True)}">'); stack.append(("LINK","a"))
                else: out.append(html.escape(match.group(0)))
            else: out.append(html.escape(match.group(0)))
        elif tag in TAG_MAP:
            tagname=TAG_MAP[tag]
            if closing and stack and stack[-1][0]==tag: out.append(f"</{tagname}>"); stack.pop()
            elif not closing: out.append(f"<{tagname}>"); stack.append((tag,tagname))
            else: out.append(html.escape(match.group(0)))
        pos=match.end()
    segment=source[pos:]; in_code=any(tag in {"CODE","PRE"} for tag,_ in stack)
    out.append(html.escape(segment.translate(SMALL_CAPS) if small_caps and not in_code else segment))
    while stack:
        _tag,tagname=stack.pop(); out.append(f"</{tagname}>")
    return "".join(out)
def caption_chunks(source:str,small_caps:bool=True,limit:int=900)->list[str]:
    if len(source)<=limit: return [render_text(source,small_caps)]
    chunks=[]; remaining=source
    while remaining:
        if len(remaining)<=limit: part,remaining=remaining,""
        else:
            cut=remaining.rfind("\n",0,limit)
            if cut<limit//2: cut=remaining.rfind(" ",0,limit)
            if cut<limit//2: cut=limit
            part,remaining=remaining[:cut],remaining[cut:].lstrip()
        chunks.append(render_text(part,small_caps))
    return chunks
