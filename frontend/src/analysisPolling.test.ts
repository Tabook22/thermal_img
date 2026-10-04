import {afterEach,expect,it,vi} from 'vitest';
import {watchAnalysis} from './analysisPolling';
afterEach(()=>vi.useRealTimers());
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>{resolve=done});return {promise,resolve}}
it('ignores an in-flight analysis after the image is closed or changed',async()=>{
  vi.useFakeTimers();const pending=deferred<{status:string}>(),onAnalysis=vi.fn(),onRegions=vi.fn();
  const stop=watchAnalysis({load:()=>pending.promise,regions:async()=>[],onAnalysis,onRegions,onError:vi.fn()});
  await vi.advanceTimersByTimeAsync(800);stop();pending.resolve({status:'completed'});await Promise.resolve();
  expect(onAnalysis).not.toHaveBeenCalled();expect(onRegions).not.toHaveBeenCalled();
});
it('ignores stale regions and never overlaps slow polls',async()=>{
  vi.useFakeTimers();const pending=deferred<number[]>(),onAnalysis=vi.fn(),onRegions=vi.fn(),load=vi.fn(async()=>({status:'completed'}));
  const stop=watchAnalysis({load,regions:()=>pending.promise,onAnalysis,onRegions,onError:vi.fn()});
  await vi.advanceTimersByTimeAsync(5000);expect(load).toHaveBeenCalledTimes(1);stop();pending.resolve([1]);await Promise.resolve();
  expect(onAnalysis).not.toHaveBeenCalled();expect(onRegions).not.toHaveBeenCalled();
});
it('recovers after a connection error and delivers the matching analysis and regions',async()=>{
  vi.useFakeTimers();const onAnalysis=vi.fn(),onRegions=vi.fn(),onError=vi.fn(),load=vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({status:'completed'});
  const stop=watchAnalysis({load,regions:async()=>[9],onAnalysis,onRegions,onError});
  await vi.advanceTimersByTimeAsync(5000);
  expect(load).toHaveBeenCalledTimes(2);expect(onError).toHaveBeenCalledTimes(1);expect(onAnalysis).toHaveBeenCalledWith({status:'completed'});expect(onRegions).toHaveBeenCalledWith([9]);stop();
});
