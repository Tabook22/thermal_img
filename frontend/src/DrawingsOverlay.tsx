import {useRef} from 'react';
import './drawings.css';

export type DrawingPoint={x:number;y:number};
export type ImageDrawing={id:string;kind:'freehand'|'line'|'ellipse'|'arrow';points:DrawingPoint[];control?:DrawingPoint|null;color:string;stroke_width:number};
export type DrawingDraft=Omit<ImageDrawing,'id'>;

const px=(p:DrawingPoint)=>`${p.x*1000} ${p.y*1000}`;
const midpoint=(a:DrawingPoint,b:DrawingPoint)=>({x:(a.x+b.x)/2,y:(a.y+b.y)/2});

export default function DrawingsOverlay({drawings,draft,selectedId,tool,onSelect,onDelete,onEditArrow,onMove,onControl,onEndpoint,onControlEnd}:{drawings:ImageDrawing[];draft:DrawingDraft|null;selectedId?:string;tool:string;onSelect:(id:string)=>void;onDelete:(id:string)=>void;onEditArrow:(id:string,event:React.MouseEvent)=>void;onMove:(id:string,event:React.PointerEvent)=>void;onControl:(id:string,event:React.PointerEvent)=>void;onEndpoint:(id:string,index:0|1,event:React.PointerEvent)=>void;onControlEnd:(id:string)=>void}){
 const bending=useRef<{id:string;pointerId:number}|null>(null);
 const endpointDrag=useRef<{id:string;index:0|1;pointerId:number}|null>(null);
 const endpoint=(id:string,index:0|1,point:DrawingPoint)=><circle className="drawingEndpoint" cx={point.x*1000} cy={point.y*1000} r="13" aria-label={index===0?'Move arrow start':'Move arrow tip'} onPointerDown={event=>{event.stopPropagation();event.currentTarget.setPointerCapture(event.pointerId);endpointDrag.current={id,index,pointerId:event.pointerId}}} onPointerMove={event=>{if(endpointDrag.current?.pointerId===event.pointerId){event.stopPropagation();onEndpoint(id,index,event)}}} onPointerUp={event=>{if(endpointDrag.current?.pointerId===event.pointerId){event.stopPropagation();onEndpoint(id,index,event);endpointDrag.current=null;onControlEnd(id)}}} onPointerCancel={event=>{if(endpointDrag.current?.pointerId===event.pointerId){event.stopPropagation();endpointDrag.current=null;onControlEnd(id)}}}/>;
 const render=(drawing:ImageDrawing|DrawingDraft,key:string,selected=false)=>{
  const [a,b]=drawing.points,control=drawing.control||midpoint(a,b);
  const curveControl={x:2*control.x-(a.x+b.x)/2,y:2*control.y-(a.y+b.y)/2};
  const path=drawing.kind==='freehand'?`M ${drawing.points.map(px).join(' L ')}`:drawing.kind==='arrow'&&drawing.control?`M ${px(a)} Q ${px(curveControl)} ${px(b)}`:`M ${px(a)} L ${px(b)}`;
  const oval={cx:(a.x+b.x)*500,cy:(a.y+b.y)*500,rx:Math.abs(a.x-b.x)*500,ry:Math.abs(a.y-b.y)*500};
  const editable=!!('id' in drawing)&&(tool==='select'||tool==='delete');
  const activate=(event:React.PointerEvent)=>{if(!editable)return;event.stopPropagation();if(tool==='delete')onDelete((drawing as ImageDrawing).id);else {onSelect((drawing as ImageDrawing).id);event.currentTarget.setPointerCapture(event.pointerId)}};
  const shape=drawing.kind==='ellipse'?<ellipse {...oval}/>:<path d={path} markerEnd={drawing.kind==='arrow'?'url(#drawing-arrow-tip)':undefined}/>;
  return <g key={key} className={`drawingShape ${selected?'selected':''}`}>
   <g className="drawingVisible" fill="none" stroke={drawing.color} strokeWidth={drawing.stroke_width} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke">{shape}</g>
   {editable&&<g className="drawingHit" onPointerDown={activate} onDoubleClick={event=>{if(tool==='select'&&drawing.kind==='arrow'){event.stopPropagation();onEditArrow((drawing as ImageDrawing).id,event)}}} onPointerMove={event=>{if(event.buttons===1&&tool==='select'){event.stopPropagation();onMove((drawing as ImageDrawing).id,event)}}} onPointerUp={event=>{if(tool==='select')onControlEnd((drawing as ImageDrawing).id)}} fill="none" stroke="transparent" strokeWidth="20" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke">{drawing.kind==='ellipse'?<ellipse {...oval}/>:<path d={path}/>}</g>}
   {selected&&editable&&<>
    {drawing.kind==='arrow'&&<>{endpoint((drawing as ImageDrawing).id,0,a)}{endpoint((drawing as ImageDrawing).id,1,b)}</>}
    {drawing.kind==='arrow'&&<circle className="drawingBend" cx={control.x*1000} cy={control.y*1000} r="20" aria-label="Drag to bend arrow" onPointerDown={event=>{event.stopPropagation();event.currentTarget.setPointerCapture(event.pointerId);bending.current={id:(drawing as ImageDrawing).id,pointerId:event.pointerId}}} onPointerMove={event=>{if(bending.current?.pointerId===event.pointerId){event.stopPropagation();onControl((drawing as ImageDrawing).id,event)}}} onPointerUp={event=>{if(bending.current?.pointerId===event.pointerId){event.stopPropagation();bending.current=null;onControlEnd((drawing as ImageDrawing).id)}}} onPointerCancel={event=>{if(bending.current?.pointerId===event.pointerId){event.stopPropagation();bending.current=null;onControlEnd((drawing as ImageDrawing).id)}}}/>}
   </>}
  </g>;
 };
 return <svg className="imageDrawings" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Image drawings"><defs><marker id="drawing-arrow-tip" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth"><path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="context-stroke" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/></marker></defs>{drawings.map(d=>render(d,d.id,d.id===selectedId))}{draft&&render(draft,'draft')}</svg>;
}
