"use strict";
const $ = id => document.getElementById(id);
let token, current, dirty = false, busy = false;
const fields = ["id","version","classes","merge","min_height_px","near_threshold_px","iou_loose","required_attributes","rules","visual_rules","unclear","facts"];
const groups = [
  ["merge","Gộp class",["class","target"],{}],
  ["min_height_px","Chiều cao tối thiểu",["class","value"],{}],
  ["rules","Luật kiểm bằng code",["id","check","message","page","quote"],{id:"R1",check:"class_not_allowed",message:"",page:1,quote:""}],
  ["visual_rules","Luật cần nhìn ảnh",["id","category","question","page","quote"],{id:"V1",category:null,question:"",page:1,quote:""}],
  ["facts","Dẫn chứng cho class, ngưỡng và thuộc tính",["field","page","quote"],{field:"classes",page:1,quote:""}],
  ["unclear","Chưa rõ / chưa hỗ trợ",["category","field","note"],{category:null,field:"",note:""}]
];
const labels={class:"Class",target:"Gộp thành",value:"Ngưỡng px",id:"Mã",check:"Phép kiểm",message:"Thông báo",page:"Trang",quote:"Câu trích nguyên văn",category:"Class áp dụng",question:"Câu hỏi kiểm tra",field:"Trường",note:"Ghi chú"};
async function api(path, body) {
  const res=await fetch(path,{method:body?"POST":"GET",headers:{"X-M13-Token":token,"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});
  const data=await res.json();
  if(!res.ok)throw new Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail));
  return data;
}
function updateActions(){
  document.querySelectorAll("#content input,#content textarea,#content select,#content button").forEach(el=>el.disabled=busy);
  $("drafts").disabled=busy;$("refresh").disabled=busy;
  $("save").disabled=busy||!current;
  $("approve").disabled=busy||!current||dirty||current.approved||current.problems.length>0;
}
function feedback(message){$("status").textContent=message;$("action-feedback").textContent=message;$("error").textContent="";$("action-error").textContent="";}
function markDirty(){dirty=true;$("confirmed").checked=false;updateActions();feedback("Có chỉnh sửa chưa lưu. Lưu bản nháp mới trước khi duyệt.");}
function showError(e){$("error").textContent=e.message;$("action-error").textContent=e.message;$("action-feedback").textContent="Chưa hoàn tất. Kiểm tra lỗi bên dưới.";$("status").textContent="Chưa hoàn tất. Kiểm tra lỗi cạnh nút thao tác.";}
function rows(name){const v=current.spec[name]||{};return name==="merge"||name==="min_height_px"?Object.entries(v).map(([k,x])=>({class:k,[name==="merge"?"target":"value"]:x})):v;}
function addRow(tbody,name,columns,value){
  const row=document.createElement("tr");
  columns.forEach(key=>{
    const td=document.createElement("td");let input;
    if(key==="check"){
      input=document.createElement("select");["below_min_height","class_not_allowed","missing_attribute","model_object_missing"].forEach(check=>{const o=document.createElement("option");o.value=check;o.textContent=check;input.append(o);});
    }else input=document.createElement(["quote","message","question","note"].includes(key)?"textarea":"input");
    if(key==="page"||key==="value"){input.type="number";input.step="any";}
    input.dataset.field=key;input.value=value[key]??"";input.addEventListener("input",markDirty);td.append(input);row.append(td);
  });
  const td=document.createElement("td"),remove=document.createElement("button");remove.textContent="Xoá";remove.onclick=()=>{row.remove();markDirty();};td.append(remove);row.append(td);tbody.append(row);
}
function render(data){
  current=data;dirty=false;$("error").textContent="";$("action-error").textContent="";$("action-feedback").textContent="";$("content").hidden=false;$("confirmed").checked=false;
  $("title").textContent=`${data.spec.id} · ${data.spec.version}`;
  $("approval-status").textContent=data.approved?`Đã duyệt bởi ${data.spec.approved_by}. Sửa sẽ tạo draft mới.`:"Bản nháp · chưa duyệt";
  $("status").textContent=data.problems.length?`Chưa đạt kiểm chứng: ${data.problems.join("; ")}`:"Schema, nguồn/hash và quote đạt. Cần người duyệt kiểm ý nghĩa từng luật.";
  $("source").textContent=`Nguồn: ${data.spec.source.file} · SHA256: ${data.spec.source.sha256}`;
  $("classes").value=data.spec.classes.join(", ");$("attributes").value=(data.spec.required_attributes||[]).join(", ");
  $("near").value=data.spec.near_threshold_px??"";$("iou").value=data.spec.iou_loose??"";
  $("history").textContent=JSON.stringify(data.spec.extraction,null,2);
  $("tables").replaceChildren();
  groups.forEach(([name,title,columns,template])=>{
    const h=document.createElement("h2");h.textContent=title;const table=document.createElement("table");table.dataset.group=name;
    const head=document.createElement("tr");[...columns,""].forEach(k=>{const th=document.createElement("th");th.textContent=labels[k]||k;head.append(th);});
    const thead=document.createElement("thead");thead.append(head);table.append(thead);const body=document.createElement("tbody");table.append(body);
    rows(name).forEach(row=>addRow(body,name,columns,row));const add=document.createElement("button");add.textContent="Thêm dòng";add.onclick=()=>{addRow(body,name,columns,template);markDirty();};
    $("tables").append(h,table,add);
  });
  updateActions();
}
function content(){
  const spec=Object.fromEntries(fields.filter(k=>k in current.spec).map(k=>[k,structuredClone(current.spec[k])]));
  const split=id=>$(id).value.split(",").map(x=>x.trim()).filter(Boolean);
  spec.classes=split("classes");spec.required_attributes=split("attributes");
  for(const [id,key] of [["near","near_threshold_px"],["iou","iou_loose"]]){if($(id).value==="")delete spec[key];else spec[key]=Number($(id).value);}
  groups.forEach(([name])=>{
    const table=document.querySelector(`table[data-group="${name}"]`);
    const rows=Array.from(table.querySelectorAll("tbody tr"),row=>Object.fromEntries(Array.from(row.querySelectorAll("[data-field]"),input=>{
      const key=input.dataset.field;return[key,key==="page"||key==="value"?Number(input.value):key==="category"&&!input.value?null:input.value];
    })));
    if(name==="merge"||name==="min_height_px"){
      if(new Set(rows.map(r=>r.class)).size!==rows.length)throw new Error("Class trùng trong bảng "+name);
      spec[name]=Object.fromEntries(rows.map(r=>[r.class,r[name==="merge"?"target":"value"]]));
    }else spec[name]=rows;
  });return spec;
}
async function reload(selected){
  const drafts=await api("/api/drafts");$("drafts").replaceChildren();
  drafts.forEach(d=>{const o=document.createElement("option");o.value=d.key;o.textContent=`${d.filename} · ${d.approved?"đã duyệt":"draft"}`;$("drafts").append(o);});
  if(selected)$("drafts").value=selected;if($("drafts").value)render(await api("/api/drafts/"+$("drafts").value));
}
$("drafts").onchange=async()=>{if(dirty&&!confirm("Bỏ chỉnh sửa chưa lưu?")){ $("drafts").value=current.key;return;}try{render(await api("/api/drafts/"+$("drafts").value));}catch(e){showError(e);}};
$("refresh").onclick=()=>{if(!dirty||confirm("Bỏ chỉnh sửa chưa lưu?"))reload(current?.key).catch(showError);};
async function perform(kind){
  if(busy||!current||(kind==="approve"&&dirty))return;
  try{
    const value={revision:current.revision,reviewer:$("reviewer").value};
    if(kind==="save")value.content=content();else value.confirmed=$("confirmed").checked;
    busy=true;updateActions();feedback(kind==="save"?"Đang kiểm tra và lưu bản nháp…":"Đang kiểm tra và duyệt bản đã lưu…");
    const result=await api(`/api/drafts/${current.key}/${kind}`,value);
    render(result);
    const message=kind==="save"?`Đã lưu bản nháp mới · ${result.spec.id} ${result.spec.version} · chưa duyệt. Bản trước giữ nguyên.`:`Đã duyệt bản ${result.spec.version} bởi ${result.spec.approved_by}. Nút duyệt khóa vì bản này đã được duyệt.`;
    feedback(message);
    // Refreshing the full catalog may take longer than saving. Keep success
    // visible and preserve the result if this follow-up request fails.
    try{await reload(result.key);feedback(message);}catch(e){feedback(message+" Danh sách chưa tải lại được; bấm Tải lại danh sách.");}
  }catch(e){showError(e);}finally{busy=false;updateActions();}
}
$("save").onclick=()=>perform("save");
$("approve").onclick=()=>perform("approve");
$("pdf").onclick=async()=>{try{const res=await fetch("/source/"+current.key,{headers:{"X-M13-Token":token}});if(!res.ok)throw new Error("Không mở được PDF đã kiểm chứng");const url=URL.createObjectURL(await res.blob());window.open(url,"_blank","noopener");setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){showError(e);}};
["classes","attributes","near","iou"].forEach(id=>$(id).addEventListener("input",markDirty));
fetch("/session").then(r=>r.json()).then(async s=>{token=s.token;await reload();}).catch(showError);
