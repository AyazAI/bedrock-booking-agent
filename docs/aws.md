# Deploying the demo

Nothing in this repository deploys itself. CI does not call AWS. The Terraform file is a reference, and applying it creates resources that cost money.

The app listens on `0.0.0.0` and the port in `PORT` (default 8000). `GET /health` is the probe. It reports the provider name and the vector backend. It does not report keys, webhook secrets, or customer names.

## What has to survive a restart

FAQ text is in `knowledge/`. The process re-indexes it on startup, so a new disk is enough for answers.

Bookings live in `DATABASE_URL`. SQLite on the container disk disappears when the task is replaced, and on Render's free web service it also disappears when the service spins down. That is fine for a walkthrough. A demo that must keep bookings needs Postgres. Set `VECTOR_BACKEND=pgvector` to put the FAQ vectors in that same database. `infra/postgres-exclusion.sql` is the overlap rule Postgres can enforce; the app also checks overlaps itself so SQLite stays safe.

Leave `LLM_PROVIDER=mock` until you mean to spend money. `openai` and `bedrock` call paid APIs. An empty OpenAI key raises before any HTTP call. Bedrock uses the normal AWS credential chain on the task role, so a task role that can call `bedrock:InvokeModel` will spend money on the first chat.

## Cheapest way to show it

Prices below are copied from the provider pages named here, then multiplied out so a month is visible. They are not a quote. Check the pages again before you launch anything.

1. **This laptop, or a screen recording.** Cost is zero. `LLM_PROVIDER=mock` makes no model call. This is the right default for a hiring demo.
2. **[Render free web service](https://render.com/docs/free).** $0, with the limits on that page: 750 free instance hours per workspace per month, spin-down after 15 minutes without a request, about a minute to wake, and an ephemeral disk. Free Postgres on the same page expires 30 days after creation. A free web service cannot attach a persistent disk. Point the service at this repo, set `PORT` from Render's environment (the image already reads `PORT`), and keep `LLM_PROVIDER=mock`. Bookings reset when it sleeps. FAQ comes back from the image on boot.
3. **AWS App Runner, paused when you are not showing it.** The [App Runner pricing page](https://aws.amazon.com/apprunner/pricing/) charges provisioned memory at **$0.007 per GB-hour** in US East (N. Virginia), US East (Ohio), US West (Oregon), and Europe (Ireland), and active compute at **$0.064 per vCPU-hour** while requests are being processed. It also says you can pause and resume a service. A paused service is the cheap way to keep a URL without paying the idle memory. The page lists a 0.25 vCPU / 0.5 GB size. Idle arithmetic for one provisioned instance, 730 hours, no requests: `0.5 GB * 0.007 * 730 = $2.56`. The sample in `infra/apprunner.tf` uses 1 vCPU and 2 GB instead, because this image installs Chroma: `2 * 0.007 * 730 = $10.22` of provisioned memory if it is left running all month. Active time adds `$0.064` per vCPU-hour on top of that, with a one-minute minimum when a provisioned instance starts processing, per the same page. There is a separate monthly fee for automated deployments and a build fee for source builds; deploying an image you already built avoids the build fee. Confirm both on the pricing page.
4. **ECS Fargate is the larger bill** for a single always-on task, before a load balancer. The [Fargate pricing page](https://aws.amazon.com/fargate/pricing/) example for Linux/X86 in US East (N. Virginia) uses **$0.000011244 per vCPU-second** and **$0.000001235 per GB-second**. Times 3600, that is about **$0.04048 per vCPU-hour** and **$0.004445 per GB-hour**. A 1 vCPU / 2 GB task for 730 hours is about `1 * 0.04048 * 730 + 2 * 0.004445 * 730 = $36.04`, and the task is billed until you set the desired count to 0. A public URL usually adds an Application Load Balancer or CloudFront, priced on [their own page](https://aws.amazon.com/elasticloadbalancing/pricing/). App Runner is the smaller AWS surface for one container. ECS is the better fit when you already run a cluster and want the Postgres exclusion constraint, private subnets, and a task role with no long-lived keys.

Bedrock and OpenAI are extra and are not included in any of those figures. The model id in `.env.example` (`amazon.nova-lite-v1:0`) is a placeholder to confirm in the Bedrock console. Do not point this demo at a large Claude model unless you have looked at the [Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/) and accepted the cost.

## App Runner, by hand

1. Build the image from this repo and push it to a private ECR repository. Do not bake a `.env` into the image. `.dockerignore` already excludes `.env`.
2. Create an App Runner service from that image, port 8000, health check `GET /health`.
3. Set `LLM_PROVIDER=mock`, `VECTOR_BACKEND=chroma`, `PORT=8000`. Add `DEMO_API_KEY` only if you want `/api/bookings` locked to something other than the local default.
4. Instance role: none, while the provider stays `mock`. Add `bedrock:InvokeModel` on one model id only if you switch providers.
5. Pause the service when the demo is over.

`infra/apprunner.tf` is the same shape in Terraform. It omits the ECR access role on purpose. Fill that in when you are ready to apply, then run `terraform plan` and read it. Do not apply it as part of setting this repo up.

## ECS sketch

A Fargate service in private subnets, behind an existing load balancer, with `DATABASE_URL` pointing at RDS Postgres and `VECTOR_BACKEND=pgvector`, matches the way a real booking service should store data. Run `infra/postgres-exclusion.sql` after the `bookings` table exists (`starts_at` and `ends_at` are ISO strings today; cast them, or change the columns to `timestamptz` before you add the constraint). Give the task role Bedrock access only if `LLM_PROVIDER` includes `bedrock`. Keep the WhatsApp token in Secrets Manager, not in the task definition. The adapter stays off until `WHATSAPP_ENABLED=true` and the app secret is set. An empty secret rejects webhook posts.

## Render

Use a web service, not a static site. Build command can be empty if you deploy the Dockerfile. Start command is the image entrypoint. Set the env vars from `.env.example` and leave the secrets blank. The free instance sleeps; the first click after that waits on the cold start described in Render's free-tier page.
