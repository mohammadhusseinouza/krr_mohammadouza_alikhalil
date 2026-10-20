"""A graph neural network for night trips: GraphSAGE, made heterogeneous with
PyTorch Geometric's to_hetero, on the same splits as baseline.py.

    python gnn.py

Run from model/ after build_graph.py. About a minute.

Each trip starts from its own features (number of stops, scheduled minutes,
direction). Two rounds of message passing let it collect what its neighbours
hold: its route, service, shape, block and the stops it calls at, and, one
step further, the other trips of the same block or route, and the stops
next to its stops. A last layer turns that into a score.

to_hetero copies the model once per kind of edge. It finds the edge input by
its NAME: the forward method must call it edge_index, or every layer fails
with a misleading error about edge_index.
"""

from pathlib import Path

import torch
import torch_geometric.transforms as T
from sklearn.metrics import average_precision_score, roc_auc_score
from torch_geometric.nn import SAGEConv, to_hetero

from baseline import line
from learning_utils import precision_at_k, split_by_route, split_random

HERE = Path(__file__).resolve().parent
EPOCHS, HIDDEN = 100, 32


class SAGE(torch.nn.Module):
    """Two GraphSAGE layers and a score. (-1, -1): input sizes are read from the data."""

    def __init__(self):
        super().__init__()
        self.conv1 = SAGEConv((-1, -1), HIDDEN)
        self.conv2 = SAGEConv((-1, -1), HIDDEN)
        self.score = torch.nn.Linear(HIDDEN, 1)

    def forward(self, x, edge_index):  # the name edge_index matters to to_hetero
        h = self.conv1(x, edge_index).relu()
        h = self.conv2(h, edge_index).relu()
        return self.score(h)


def run(data, y, train, test, seed=0):
    torch.manual_seed(seed)
    model = to_hetero(SAGE(), data.metadata(), aggr="sum")
    model(data.x_dict, data.edge_index_dict)  # one pass to size the layers
    opt = torch.optim.Adam(model.parameters(), lr=0.01)
    target = torch.tensor(y, dtype=torch.float)
    weight = torch.tensor((1 - y[train].mean()) / y[train].mean())  # night trips are rare: count them more
    for _ in range(EPOCHS):
        model.train()
        opt.zero_grad()
        out = model(data.x_dict, data.edge_index_dict)["trip"].squeeze()
        torch.nn.functional.binary_cross_entropy_with_logits(out[train], target[train], pos_weight=weight).backward()
        opt.step()
    model.eval()
    with torch.no_grad():
        p = torch.sigmoid(model(data.x_dict, data.edge_index_dict)["trip"].squeeze()).numpy()[test]
    yt = y[test]
    return {"night in test": int(yt.sum()),
            "PR-AUC": average_precision_score(yt, p) if yt.sum() else float("nan"),
            "ROC-AUC": roc_auc_score(yt, p) if 0 < yt.sum() < len(yt) else float("nan"),
            "precision@100": precision_at_k(yt, p, 100), "accuracy": float(((p > 0.5) == yt).mean()),
            "parameters": sum(q.numel() for q in model.parameters())}


def main():
    b = torch.load(HERE / "data" / "halifax-graph.pt", weights_only=False)
    data = T.ToUndirected()(b["data"])  # messages flow both ways along every link
    y, route = b["y"].numpy(), b["route"].numpy()
    train, test = split_random(len(y), y)
    for s in range(3):
        r = run(data, y, train, test, seed=s)
        print(line(f"random split, training seed {s}", r))
    print(f"  ({r['parameters']:,} parameters)")
    for s in range(5):
        train, test = split_by_route(route, seed=s)
        print(line(f"split by route, seed {s}", run(data, y, train, test)))


if __name__ == "__main__":
    main()
