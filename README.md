# Kubernetes Learning Lab

A small FastAPI application designed for a home Kubernetes cluster. Its home
page shows the running Pod, its Node, Pod IP, configured cluster name, Node
inventory, Pods and Services in its namespace, and every Namespace it can read.
It uses a deliberately read-only ServiceAccount and does not request access to
Secrets or write any Kubernetes resource.

## Run locally

Local mode renders the interface and experiments, but reports that it cannot
read a Kubernetes API because no ServiceAccount is mounted.

```bash
cd kube-learning-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://localhost:8000>.

## Deploy to your cluster

Build a multi-architecture image so the same tag works on both Intel/AMD and
Apple Silicon nodes. Replace `consultomer` if your Docker Hub namespace differs.

```bash
docker buildx create --use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag consultomer/kube-learning:1.0.1 \
  --push .

kubectl apply -f kubernetes/kube-learning.yaml
kubectl -n kube-learning rollout status deployment/kube-learning
kubectl -n kube-learning get pods -o wide
```

The manifest exposes the lab through NodePort `30080`. For the cluster in this
workspace, open:

```text
http://192.168.178.76:30080/
```

Any node IP can normally serve a NodePort. Ensure the VM or host firewall permits
TCP `30080` from your browser.

## Exercises

### 1. Observe Service load balancing

The dashboard calls `http://kube-learning` (its own in-cluster Service) multiple
times with fresh HTTP connections. Each result identifies the Pod and Node that
served it. You should see multiple Pod names after several runs.

You can also test externally:

```bash
for i in $(seq 1 20); do
  curl -s http://192.168.178.76:30080/api/whoami
  echo
done
```

Scale the replicas and repeat:

```bash
kubectl -n kube-learning scale deployment/kube-learning --replicas=5
kubectl -n kube-learning get pods -o wide
```

### 2. Observe rate limiting

The rate-limit button uses an in-memory limit of 8 requests per 30 seconds. Its
response identifies the replica that made the decision. Because each replica has
its own memory, a Service can route you to a different replica with a fresh
counter. That limitation is intentional: it illustrates why production rate
limiting normally belongs in a shared store or API gateway.

### 3. Inspect the API access boundary

The dashboard can list Nodes, Pods, Services, and Namespaces. Inspect the
read-only permissions from the control-plane machine:

```bash
kubectl auth can-i list nodes \
  --as=system:serviceaccount:kube-learning:kube-learning
kubectl auth can-i get secrets \
  --as=system:serviceaccount:kube-learning:kube-learning
```

The first command should return `yes`; the second should return `no`.

## Cleanup

```bash
kubectl delete -f kubernetes/kube-learning.yaml
```
