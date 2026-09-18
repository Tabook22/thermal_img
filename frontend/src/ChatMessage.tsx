import {BookOpen,Globe2,Sparkles,UserRound} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export type LibraryResult={document_id:string;filename:string;page:number;locator:string;excerpt:string};
export type WebResult={title?:string;url?:string};
export type Message={role:'assistant'|'user';text:string;origin?:'image'|'library'|'web'|'error';sources?:LibraryResult[];webSources?:WebResult[]};

const tidyMarkdown=(text:string)=>text
 .replace(/\\([*_[\]()])/g,'$1')
 .replace(/\]\(\[(https?:\/\/[^\]\s]+)\]\((https?:\/\/[^)\s]+)\)\)/g,']($2)')
 .replace(/\)(?=[A-Z][a-z])/g,') ');

const safeWebUrl=(url?:string)=>url&&/^https?:\/\//i.test(url)?url:null;

export default function ChatMessage({message}: {message:Message}){
 const isUser=message.role==='user';
 const label=isUser?'You':message.origin==='web'?'Web research':message.origin==='library'?'Local library':message.origin==='error'?'Search notice':'Inspection assistant';
 const webSources=Array.from(new Map((message.webSources||[]).filter(source=>safeWebUrl(source.url)).map(source=>[source.url!,source])).values());
 return <article className={`imageChatMessage ${message.role}${message.origin==='error'?' error':''}`} aria-label={`${label} message`}>
  <div className="imageChatMessageHeader"><span className="imageChatMessageAvatar">{isUser?<UserRound size={14}/>:message.origin==='web'?<Globe2 size={14}/>:message.origin==='library'?<BookOpen size={14}/>:<Sparkles size={14}/>}</span><span>{label}</span></div>
  <div className="imageChatMessageBody">{isUser?<p>{message.text}</p>:<ReactMarkdown remarkPlugins={[remarkGfm]} components={{a:({href,children})=>safeWebUrl(href)?<a href={href} target="_blank" rel="noopener noreferrer">{children}</a>:<span>{children}</span>}}>{tidyMarkdown(message.text)}</ReactMarkdown>}</div>
  {!!message.sources?.length&&<div className="imageChatReferences"><strong>From your library</strong>{message.sources.map((source,index)=><div className="imageChatSource" key={`${source.document_id}-${source.page}-${index}`}><a href={`/api/library/documents/${source.document_id}/file${source.filename.toLowerCase().endsWith('.pdf')?`#page=${source.page}`:''}`} target="_blank" rel="noreferrer">{source.filename} · {source.locator}</a><p>{source.excerpt}</p></div>)}</div>}
  {!!webSources.length&&<div className="imageChatReferences"><strong>Web sources</strong>{webSources.map((source,index)=><div className="imageChatWebSource" key={`${source.url}-${index}`}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title||source.url}</a></div>)}</div>}
 </article>;
}
