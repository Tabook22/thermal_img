import {beforeEach,afterEach,expect,it,vi} from 'vitest';
import {api} from './api';

vi.mock('./api',()=>({api:vi.fn()}));
const recent={id:1,tower_code:'Previous inspection',created_at:''};
const clicked={id:42,name:'Clicked thermal.jpg',classification:'thermal',sha256:'source',preview_url:'/api/images/42/preview'};
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>{resolve=done});return {promise,resolve}}

beforeEach(()=>{
  vi.resetModules();vi.mocked(api).mockReset();
  vi.stubGlobal('location',{hash:'#inspection=ticket-a',search:''});
  vi.stubGlobal('history',{replaceState:vi.fn()});
});
afterEach(()=>vi.unstubAllGlobals());

it.each(['before','after'])('opens the clicked image when recent inspections finish %s the transfer',async order=>{
  const list=deferred<unknown>(),transfer=deferred<unknown>();
  vi.mocked(api).mockImplementation(path=>path==='/api/inspection-bridge/open'?transfer.promise:list.promise as any);
  const {loadInitialWorkspace}=await import('./workspaceStartup');
  const received=vi.fn(),result=loadInitialWorkspace(7,received);
  if(order==='before')list.resolve([recent]);
  transfer.resolve({image:clicked});
  expect(await result).toEqual(clicked);
  if(order==='after')list.resolve([recent]);
  await Promise.resolve();
  expect(received).toHaveBeenCalledWith([recent]);
  expect(api).toHaveBeenCalledTimes(2);
  expect(api).not.toHaveBeenCalledWith('/api/inspections/1/images');
});

it('reports a failed transfer without loading the previous image',async()=>{
  vi.mocked(api).mockImplementation(path=>path==='/api/inspection-bridge/open'?Promise.reject(new Error('Editing link expired')):Promise.resolve([recent]) as any);
  const {loadInitialWorkspace}=await import('./workspaceStartup');
  await expect(loadInitialWorkspace(7,vi.fn())).rejects.toThrow('Editing link expired');
  expect(api).not.toHaveBeenCalledWith('/api/inspections/1/images');
});

it('resumes the exact linked image on refresh',async()=>{
  vi.stubGlobal('location',{hash:'',search:'?inspection_image=42'});
  vi.mocked(api).mockImplementation(path=>Promise.resolve(path==='/api/inspections'?[recent]:{image:clicked}) as any);
  const {loadInitialWorkspace}=await import('./workspaceStartup');
  expect(await loadInitialWorkspace(7,vi.fn())).toEqual(clicked);
  expect(api).toHaveBeenCalledWith('/api/inspection-bridge/images/42');
  expect(api).not.toHaveBeenCalledWith('/api/inspections/1/images');
});

it('deduplicates StrictMode ticket claims but opens each different launch',async()=>{
  const transfer=deferred<any>();
  vi.mocked(api).mockReturnValue(transfer.promise);
  const {openInspectionImage}=await import('./workspaceStartup');
  const first=openInspectionImage(7);
  expect(openInspectionImage(7)).toBe(first);
  expect(api).toHaveBeenCalledTimes(1);
  transfer.resolve({image:clicked});await first;
  location.hash='#inspection=ticket-b';
  const second=openInspectionImage(7);
  expect(second).not.toBe(first);
  expect(api).toHaveBeenCalledTimes(2);
  expect(JSON.parse(vi.mocked(api).mock.calls[1][1]!.body as string).ticket).toBe('ticket-b');
  await second;
});

it('opens a recent image only for a normal standalone visit',async()=>{
  vi.stubGlobal('location',{hash:'',search:''});
  vi.mocked(api).mockImplementation(path=>Promise.resolve(path==='/api/inspections'?[recent]:[clicked]) as any);
  const {loadInitialWorkspace}=await import('./workspaceStartup');
  expect(await loadInitialWorkspace(7,vi.fn())).toEqual(clicked);
  expect(api).toHaveBeenCalledWith('/api/inspections/1/images');
});
