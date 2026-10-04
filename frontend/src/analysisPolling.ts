// Poll sequentially so a slow response cannot overtake a newer result.
export function watchAnalysis<A extends {status:string},R>(options:{load:()=>Promise<A>;regions:()=>Promise<R>;onAnalysis:(value:A)=>void;onRegions:(value:R)=>void;onError:(error:unknown)=>void;interval?:number}){
  let stopped=false;
  let timer:ReturnType<typeof setTimeout>;
  async function poll(){
    try{
      const value=await options.load();if(stopped)return;
      if(value.status==='completed'){
        const regions=await options.regions();if(stopped)return;
        options.onAnalysis(value);options.onRegions(regions);
        return;
      }
      options.onAnalysis(value);
      if(value.status==='failed')return;
    }catch(error){if(stopped)return;options.onError(error)}
    if(!stopped)timer=setTimeout(poll,options.interval??800);
  }
  timer=setTimeout(poll,options.interval??800);
  return()=>{stopped=true;clearTimeout(timer)};
}
