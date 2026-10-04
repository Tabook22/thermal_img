import {useRef,useState} from 'react';
import {FileImage,FolderOpen,Upload,Archive,ShieldCheck} from 'lucide-react';

export default function UploadWorkspace({busy,upload}:{busy:boolean;upload:(files:FileList|null)=>void}){
  const input=useRef<HTMLInputElement>(null),[dragging,setDragging]=useState(false);
  return <section className="page uploadWorkspace" aria-labelledby="upload-title"><div className="pageHead"><div><small>NEW INSPECTION</small><h1 id="upload-title">Start with your thermal image</h1><p>Upload an original camera image or reopen an editable inspection package.</p></div></div>
    <div className={`uploadDrop ${dragging?'dragging':''}`} aria-busy={busy} onDragOver={event=>{event.preventDefault();if(!busy)setDragging(true)}} onDragLeave={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node))setDragging(false)}} onDrop={event=>{event.preventDefault();setDragging(false);if(!busy)upload(event.dataTransfer.files)}}>
      <span className="uploadSymbol"><Upload size={30}/></span><h2>{busy?'Uploading and verifying…':'Drop images here'}</h2><p>DJI radiometric JPEG · JPEG · PNG · .thermalpkg</p><button className="primary" disabled={busy} onClick={()=>input.current?.click()}><FolderOpen size={17}/>{busy?'Please wait…':'Choose files'}</button>
      <input ref={input} hidden multiple type="file" accept="image/jpeg,image/png,.thermalpkg,application/vnd.tower-thermal-inspection+zip" onChange={event=>{upload(event.currentTarget.files);event.currentTarget.value=''}}/>
      <small role="status">{busy?'Keep this page open while the images are added.':'You can select several files at once.'}</small>
    </div>
    <div className="uploadGuide"><article><FileImage/><h3>Measure temperature</h3><p>Use the original DJI radiometric JPEG. Screenshots and ordinary images support visual edits but may not contain temperature data.</p></article><article><Archive/><h3>Continue saved work</h3><p>Open a .thermalpkg to restore its crop, measurements, annotations, and display settings.</p></article><article><ShieldCheck/><h3>Keep your evidence</h3><p>Your original files remain intact. Export a PNG for reports or an editable package for later work.</p></article></div>
  </section>;
}
