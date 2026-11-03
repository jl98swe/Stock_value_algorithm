import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const allowedOrigin = "https://jl98swe.github.io";
const MAX_SUBSCRIBERS = 10;
const site = "https://jl98swe.github.io/Stock_value_algorithm/";
const encoder = new TextEncoder();
const topicsAllowed = ["signals","near_signals","reports_upcoming","reports_updated","stop_loss","data_issues"];
const strategiesAllowed = ["all","standard","standard_stop_loss_10","ma200","report_avoidance"];

function headers(origin: string | null) {
  return {"Content-Type":"application/json","Cache-Control":"no-store","Access-Control-Allow-Origin":origin === allowedOrigin ? allowedOrigin : allowedOrigin,"Access-Control-Allow-Methods":"GET,POST,OPTIONS","Access-Control-Allow-Headers":"content-type"};
}
function json(data: unknown, status=200, origin: string | null=null) {
  return new Response(JSON.stringify(data),{status,headers:headers(origin)});
}
function randomToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return Array.from(bytes, x => x.toString(16).padStart(2,"0")).join("");
}
async function digest(token: string) {
  const hash = await crypto.subtle.digest("SHA-256",encoder.encode(token));
  return Array.from(new Uint8Array(hash),x=>x.toString(16).padStart(2,"0")).join("");
}
function page(message: string) {
  return new Response('<!doctype html><html lang="sv"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Bevakningar</title><body style="font:18px system-ui;max-width:38rem;margin:4rem auto;padding:1rem"><h1>Stock Value Algorithm</h1><p>'+message+'</p><p><a href="'+site+'alerts.html">Tillbaka till notiser</a></p></body></html>',{headers:{"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store","Referrer-Policy":"no-referrer"}});
}
Deno.serve(async (request) => {
  const origin=request.headers.get("origin");
  if (request.method==="OPTIONS") return new Response(null,{status:204,headers:headers(origin)});
  if (origin && origin!==allowedOrigin) return json({error:"origin"},403,origin);
  const url=new URL(request.url);
  const action=url.pathname.split("/").filter(Boolean).at(-1);
  const dbUrl=Deno.env.get("SUPABASE_URL");
  const dbKey=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!dbUrl || !dbKey) return json({error:"not_configured"},503,origin);
  const db=createClient(dbUrl,dbKey,{auth:{persistSession:false,autoRefreshToken:false}});
  if (request.method==="GET" && (action==="confirm" || action==="unsubscribe")) {
    const token=url.searchParams.get("token")||"";
    if (!/^[a-f0-9]{64}$/.test(token)) return page("Länken är ogiltig eller har gått ut.");
    const tokenHash=await digest(token);
    const {data:t,error:te}=await db.from("alert_tokens").select("subscriber_id,expires_at,consumed_at").eq("token_hash",tokenHash).eq("purpose",action).maybeSingle();
    if (te || !t || t.consumed_at || Date.parse(t.expires_at)<Date.now()) return page("Länken är ogiltig eller har gått ut.");
    const {data:used,error:ue}=await db.from("alert_tokens").update({consumed_at:new Date().toISOString()}).eq("token_hash",tokenHash).is("consumed_at",null).select("subscriber_id").maybeSingle();
    if (ue || !used) return page("Länken har redan använts.");
    const fields=action==="confirm" ? {status:"active",confirmed_at:new Date().toISOString(),updated_at:new Date().toISOString()} : {status:"unsubscribed",unsubscribed_at:new Date().toISOString(),updated_at:new Date().toISOString()};
    const {error:se}=await db.from("alert_subscribers").update(fields).eq("id",t.subscriber_id);
    if (se) return page("Ett fel uppstod. Kontakta webbplatsens ansvariga.");
    return page(action==="confirm" ? "Din mejladress är bekräftad och bevakningen är aktiv." : "Din prenumeration har avslutats.");
  }
  if (request.method!=="POST" || action!=="subscribe") return json({error:"not_found"},404,origin);
  const generic={message:"Om adressen kan registreras skickas ett bekräftelsemejl."};
  if (Number(request.headers.get("content-length")||0)>8192) return json({error:"too_large"},413,origin);
  let body: Record<string,unknown>;
  try { body=await request.json(); } catch { return json({error:"invalid_json"},400,origin); }
  const email=typeof body.email==="string" ? body.email.trim().toLowerCase() : "";
  const channels=body.channels;
  const topics=body.topics;
  const strategy=body.strategy;
  const tickers=body.tickers;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length>254 ||
      body.consent!==true || !Array.isArray(channels) || channels.length!==1 || channels[0]!=="email" ||
      !Array.isArray(topics) || topics.length<1 || topics.length>topicsAllowed.length || !topics.every(x=>topicsAllowed.includes(x)) ||
      !strategiesAllowed.includes(String(strategy)) || !Array.isArray(tickers) || tickers.length>100 ||
      !tickers.every(x=>typeof x==="string" && /^[A-Z0-9.-]{1,24}$/.test(x))) {
    return json({error:"invalid_input"},400,origin);
  }
  const {data:existing,error:lookupError}=await db.from("alert_subscribers").select("id,status,updated_at").eq("email_normalized",email).maybeSingle();
  if (lookupError) return json({error:"database_unavailable"},503,origin);
  if (existing?.status==="active") return json(generic,200,origin);
  if (existing && Date.now()-Date.parse(existing.updated_at)<15*60*1000) return json(generic,200,origin);
  if (!existing) {
    const {count, error:capacityError}=await db.from("alert_subscribers").select("id",{count:"exact",head:true}).in("status",["pending","active"]);
    if (capacityError) return json({error:"database_unavailable"},503,origin);
    if ((count ?? MAX_SUBSCRIBERS) >= MAX_SUBSCRIBERS) return json(generic,200,origin);
  }
  let subscriberId=existing?.id;
  if (!subscriberId) {
    const {data:created,error:ce}=await db.from("alert_subscribers").insert({email,status:"pending"}).select("id").single();
    if (ce) return json({error:"database_unavailable"},503,origin);
    subscriberId=created.id;
  } else {
    const {error:ue}=await db.from("alert_subscribers").update({status:"pending",consent_at:new Date().toISOString(),updated_at:new Date().toISOString()}).eq("id",subscriberId);
    if (ue) return json({error:"database_unavailable"},503,origin);
  }
  const {error:pe}=await db.from("alert_preferences").upsert({subscriber_id:subscriberId,channels,topics,strategy,tickers,updated_at:new Date().toISOString()});
  if (pe) return json({error:"database_unavailable"},503,origin);
  const token=randomToken();
  const unsubscribeToken=randomToken();
  const tokenHash=await digest(token);
  const {error:te}=await db.from("alert_tokens").insert({token_hash:tokenHash,subscriber_id:subscriberId,purpose:"confirm",expires_at:new Date(Date.now()+24*60*60*1000).toISOString()});
  if (te) return json({error:"database_unavailable"},503,origin);
  const {error:unsubError}=await db.from("alert_tokens").insert({token_hash:await digest(unsubscribeToken),subscriber_id:subscriberId,purpose:"unsubscribe",expires_at:new Date(Date.now()+365*24*60*60*1000).toISOString()});
  if (unsubError) return json({error:"database_unavailable"},503,origin);
  const confirmationUrl=new URL(request.url);
  confirmationUrl.pathname="/functions/v1/alerts/confirm";
  confirmationUrl.search="?token="+token;
  const unsubscribeUrl=new URL(confirmationUrl.toString());
  unsubscribeUrl.pathname="/functions/v1/alerts/unsubscribe";
  unsubscribeUrl.search="?token="+unsubscribeToken;
  const {error:queueError}=await db.from("alert_email_queue").insert({
    subscriber_id:subscriberId,
    recipient:email,
    subject:"Bekräfta dina bevakningar – Stock Value Algorithm",
    body:"Bekräfta din mejladress inom 24 timmar:\n"+confirmationUrl.toString()+"\n\nAvsluta prenumerationen: "+unsubscribeUrl.toString()+"\n\nOm du inte begärt detta kan du bortse från mejlet.",
    status:"pending"
  });
  if (queueError) return json({error:"queue_unavailable"},503,origin);
  return json(generic,200,origin);
});
