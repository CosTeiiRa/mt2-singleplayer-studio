/** Poll repository work without retaining control of a page after navigation. */
export const jobActive=job=>['queued','running'].includes(job?.status);
export function transferLabel(job){
  const progress=job?.progress;
  if(!progress||!progress.received_bytes&&!progress.total_bytes)return '';
  const size=value=>`${(value/1024).toFixed(1)} KiB`;
  return `${size(progress.received_bytes??0)} received${progress.total_bytes!=null?' / '+size(progress.total_bytes):''}`;
}
export async function watchJob({getJob,isCurrent,onUpdate,onFinish,delay=()=>new Promise(resolve=>setTimeout(resolve,800))}){
  while(isCurrent()){
    const job=await getJob();
    if(!isCurrent())return;
    onUpdate(job);
    if(!jobActive(job)){await onFinish(job);return;}
    await delay();
  }
}
