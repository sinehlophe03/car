document.addEventListener('DOMContentLoaded', ()=>{
  const d=document.querySelector('input[type=date]');
  if(d){ const t=new Date(); t.setDate(t.getDate()+1); d.valueAsDate=t; }
});
