// One optional mount prefix. Scientific source strings and external URLs are untouched.
const EVIDA_BASE = location.pathname === '/preview' || location.pathname.startsWith('/preview/') ? '/preview' : '';
function deploymentURL(value){
  const path=String(value??'');
  if(!path.startsWith('/')||path.startsWith('//')||!EVIDA_BASE||path===EVIDA_BASE||path.startsWith(EVIDA_BASE+'/'))return path;
  return EVIDA_BASE+path;
}
function deploymentHTML(html){return String(html).replace(/\b(href|src)=(['"])(\/(?!\/)[^'"]*)\2/g,(_match,attr,quote,url)=>`${attr}=${quote}${deploymentURL(url)}${quote}`)}
const evidaStorage={
  getItem:key=>localStorage.getItem((EVIDA_BASE?'evida-preview:':'')+key),
  setItem:(key,value)=>localStorage.setItem((EVIDA_BASE?'evida-preview:':'')+key,value),
  removeItem:key=>localStorage.removeItem((EVIDA_BASE?'evida-preview:':'')+key)
};
