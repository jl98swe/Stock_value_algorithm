// Subscription endpoint placeholder pending email provider configuration.
Deno.serve(() => new Response(JSON.stringify({error: 'not_configured'}), {status: 503, headers: {'Content-Type': 'application/json'}}));
