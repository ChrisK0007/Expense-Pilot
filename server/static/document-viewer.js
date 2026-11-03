'use strict';
const DocumentViewer=(()=>{
 let revision=0;
 async function open(id){
  document.querySelector('#document-viewer')?.remove();
  const token=++revision,dialog=document.createElement('dialog');dialog.id='document-viewer';dialog.className='document-viewer';
  dialog.innerHTML=`<div class="preview-heading"><h2 id="document-view-title">Document preview</h2><button type="button" class="ghost" aria-label="Close document preview">Close</button></div><p id="document-view-filename" class="muted"></p><div class="preview-controls"><a class="button-link secondary" href="/api/documents/${encodeURIComponent(id)}/download">Download original</a><span id="document-page-controls"></span></div><p id="document-view-notice" class="footnote" role="status"></p><div id="document-view-stage" class="document-view-stage"><p>Loading preview…</p></div>`;
  dialog.setAttribute('aria-labelledby','document-view-title');document.body.append(dialog);
  dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>{if(token===revision)++revision;dialog.remove();};dialog.showModal();
  const stage=dialog.querySelector('#document-view-stage'),notice=dialog.querySelector('#document-view-notice');
  try{
   const data=await api(`documents/${encodeURIComponent(id)}/view`);if(token!==revision)return;
   dialog.querySelector('h2').textContent=data.title;dialog.querySelector('#document-view-filename').textContent=data.filename;
   notice.textContent=[data.notice,data.truncated?'This preview is shortened. Download the original to see all content.':''].filter(Boolean).join(' ');
   if(data.kind==='pdf'||data.kind==='image'){
    let current=1,zoom=false;
    dialog.querySelector('#document-page-controls').innerHTML=`${data.kind==='pdf'?'<button type="button" class="secondary" id="document-prev">Previous</button><label for="document-page-number">Page</label><input type="number" id="document-page-number" min="1" max="'+data.pages+'" value="1"><span>of '+data.pages+'</span><button type="button" class="secondary" id="document-next">Next</button>':''}<button type="button" class="secondary" id="document-zoom">Zoom in</button>`;
    function draw(){
     stage.replaceChildren();const img=document.createElement('img');img.alt=`${data.filename}, page ${current}`;img.className=zoom?'document-page zoomed':'document-page';
     img.onerror=()=>{if(token===revision){stage.innerHTML='<p class="error">This page could not be displayed. Try another page or download the original.</p>';}};
     img.src=`/api/documents/${encodeURIComponent(id)}/page?page=${current}`;stage.append(img);stage.scrollTo(0,0);
     const input=dialog.querySelector('#document-page-number');if(input){input.value=current;dialog.querySelector('#document-prev').disabled=current===1;dialog.querySelector('#document-next').disabled=current===data.pages;}
    }
    const input=dialog.querySelector('#document-page-number');if(input){input.onchange=()=>{const number=Number(input.value);if(Number.isInteger(number)&&number>=1&&number<=data.pages){current=number;draw();}else input.value=current;};dialog.querySelector('#document-prev').onclick=()=>{current--;draw();};dialog.querySelector('#document-next').onclick=()=>{current++;draw();};}
    dialog.querySelector('#document-zoom').onclick=e=>{zoom=!zoom;e.target.textContent=zoom?'Fit width':'Zoom in';stage.querySelector('img')?.classList.toggle('zoomed',zoom);};draw();
   }else if(data.kind==='sheets'){
    const controls=dialog.querySelector('#document-page-controls');controls.innerHTML='<label for="document-sheet">Sheet</label><select id="document-sheet">'+data.sheets.map((s,i)=>`<option value="${i}">${esc(s.name)}</option>`).join('')+'</select>';
    function sheet(index){const rows=data.sheets[index]?.rows||[];stage.innerHTML=rows.length?'<table class="document-values"><tbody>'+rows.map((r,i)=>'<tr><th scope="row">'+(i+1)+'</th>'+r.map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>':'<p>No cell values are available in this preview.</p>';}
    controls.querySelector('select').onchange=e=>sheet(Number(e.target.value));sheet(0);
   }else{const pre=document.createElement('pre');pre.className='document-text';pre.textContent=data.text||'No text is available in this preview.';stage.replaceChildren(pre);}
  }catch(error){if(token===revision){stage.innerHTML='<p class="error"></p>';stage.querySelector('p').textContent=error.message;}}
 }
 return {open};
})();
