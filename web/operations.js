/* Shared operation presentation; a completed step is never a duration estimate. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;else root.StudioOperations=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const allowed=new Set(['pending','running','complete','failed','warning','blocked']);
  function elapsed(job,now=Date.now()/1000){
    if(!Number.isFinite(job?.started))return '';
    if(job.status&&job.status!=='running'&&!Number.isFinite(job.finished))return '';
    const seconds=Math.max(0,Math.floor((job.finished??now)-job.started));
    return seconds<60?seconds+'s':Math.floor(seconds/60)+'m '+String(seconds%60).padStart(2,'0')+'s';
  }
  function view(job={},options={}){
    const validation=options.starting==='validation'||!options.starting&&(job.kind==='validation'||job.status==='validated');
    const kind=validation?'Build validation':job.kind==='combined'?'Files & add-ons':job.kind==='addons'?'Add-on Apply':'Server Apply',pending=Number(options.pending)||0;
    const active=!!options.starting||job.status==='running';
    const steps=Array.isArray(job.progress?.steps)?job.progress.steps.filter(step=>step&&typeof step.label==='string').map(step=>({
      id:String(step.id),label:step.label,detail:typeof step.detail==='string'?step.detail:'',status:allowed.has(step.status)?step.status:'pending'
    })):[];
    if(['succeeded','validated','failed','unverified','interrupted'].includes(job.status)){
      for(const step of steps){
        if(step.status==='running')step.status=job.status==='failed'?'failed':['unverified','interrupted'].includes(job.status)?'warning':'complete';
        else if(step.status==='pending')step.status='blocked';
      }
    }
    const current=steps.find(step=>step.id===job.progress?.current);
    const complete=steps.filter(step=>step.status==='complete').length;
    let tone=active?'working':'neutral',title=kind,message='',attention=false;
    if(options.starting){title=validation?'Starting build validation…':'Starting Server Apply…';message='Waiting for Studio to start the operation.';}
    else if(active){title=current?.label||kind+' in progress';message=current?.detail||(validation?'Checking compilation. The game will keep running.':'Preparing the saved configuration.');}
    else if(job.status==='succeeded'){tone='success';title=kind+' complete';message=job.kind==='addons'?'Client add-ons were applied and verified. You can reopen the game client.':job.kind==='combined'?'Server files and client add-ons were applied and verified. You can reopen the game client.':'Game health and deployed content checks passed.';}
    else if(job.status==='validated'){tone='success';title='Build validation passed';message='Compilation passed. Changes were not applied and the game was not restarted.';}
    else if(job.status==='failed'){tone='danger';title=kind+' failed';message=current?'Stopped at '+current.label+'. Saved changes and backups are retained.':'Saved changes and backups are retained. Open the log for the failure details.';attention=true;}
    else if(job.status==='unverified'){tone='warning';title='Apply needs verification';message='Commands finished, but game health or content checks did not pass. Saved changes remain pending.';attention=true;}
    else if(job.status==='interrupted'){tone='warning';title='Server Apply interrupted';message='Check the game launcher and running build commands before retrying. Saved changes remain pending.';attention=true;}
    if(job.serverStatus==='succeeded'&&job.addons?.status==='failed')message='Server files were applied successfully. Only client add-ons still need attention. Open the log, then review add-ons again.';
    if(job.serverStatus==='succeeded'&&job.status==='interrupted'){title='Add-on Apply interrupted';message='Server files were applied successfully. Check installed add-ons to verify the client files before retrying.';}
    if(job.kind==='addons'&&job.status==='interrupted'){title='Add-on Apply interrupted';message='Check installed add-ons to verify the client files before retrying.';}
    if(options.connectionFailed){tone='warning';title=active?'Connection lost · operation status unknown':'Could not refresh operation status';message='Reconnect to check the result. Studio has not confirmed completion.';attention=true;}
    if(pending)message+=active&&!validation?` ${pending} saved ${pending===1?'change stays':'changes stay'} pending until Apply is verified.`:` ${pending} saved ${pending===1?'change still needs':'changes still need'} Apply.`;
    return {kind,active,tone,title,message,attention,stale:!!options.connectionFailed,steps,complete,total:steps.length,elapsed:elapsed(job,options.now),
      lastLine:active&&!options.connectionFailed?(job.lines??[]).filter(line=>typeof line==='string'&&line.trim()).at(-1)||'':''};
  }
  return {view,elapsed};
});
