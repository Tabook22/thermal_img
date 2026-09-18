import {useState} from 'react';
import {Eye,EyeOff} from 'lucide-react';
import './temperature-visibility.css';

type Visibility={maximum:boolean;minimum:boolean};
const storageKey='thermal-temperature-marker-visibility';
export function useTemperatureVisibility(){
 const [visibility,setVisibility]=useState<Visibility>(()=>{
  try{const saved=JSON.parse(localStorage.getItem(storageKey)||'{}');return {maximum:saved.maximum!==false,minimum:saved.minimum!==false}}catch{return {maximum:true,minimum:true}}
 });
 const toggle=(kind:keyof Visibility)=>setVisibility(previous=>{
  const next={...previous,[kind]:!previous[kind]};
  try{localStorage.setItem(storageKey,JSON.stringify(next))}catch{/* Visibility also works when browser storage is unavailable. */}
  return next;
 });
 return {visibility,toggle};
}

export default function TemperatureVisibility({visibility,toggle,disabled}:{visibility:Visibility;toggle:(kind:keyof Visibility)=>void;disabled:boolean}){
 return <div className="temperatureVisibility" role="group" aria-label="Temperature marker visibility"><span>Show on image</span>{(['maximum','minimum'] as const).map(kind=><button type="button" key={kind} disabled={disabled} aria-label={`Show ${kind} temperature`} aria-pressed={visibility[kind]} title={`${visibility[kind]?'Hide':'Show'} ${kind} temperature markers and image labels`} onClick={()=>toggle(kind)}>{visibility[kind]?<Eye size={14}/>:<EyeOff size={14}/>}<span>{kind==='maximum'?'MAX':'MIN'}</span></button>)}</div>;
}
