import torch
import torch.nn as nn

from .SeqContext import SeqContext
from .EdgeAtt import EdgeAtt
from .GCN import GCN
from .Classifier import Classifier
from .functions import batch_graphify
import dgcn
# TODO import our fusion module.
from dgcn.model.fusion.fusionPlugin import fusionPlugin

log = dgcn.utils.get_logger()


class DialogueGCN(nn.Module):

    def __init__(self, args):
        super(DialogueGCN, self).__init__()
        # TODO utterance_dim here. 
        if args.fusion == 'concat':
            u_dim = 712
        elif args.fusion == 'tfn' or args.fusion == 'text':
            u_dim = 100

        g_dim = 200
        h1_dim = 100
        h2_dim = 100
        hc_dim = 100
        tag_size = 6

        self.wp = args.wp
        self.wf = args.wf
        self.device = args.device

        # TODO import our fusion module.
        self.fusion = fusionPlugin(args)

        self.rnn = SeqContext(u_dim, g_dim, args)
        self.edge_att = EdgeAtt(g_dim, args)
        self.gcn = GCN(g_dim, h1_dim, h2_dim, args)
        self.clf = Classifier(g_dim + h2_dim, hc_dim, tag_size, args)

        edge_type_to_idx = {}
        for j in range(args.n_speakers):
            for k in range(args.n_speakers):
                edge_type_to_idx[str(j) + str(k) + '0'] = len(edge_type_to_idx)
                edge_type_to_idx[str(j) + str(k) + '1'] = len(edge_type_to_idx)
        self.edge_type_to_idx = edge_type_to_idx
        log.debug(self.edge_type_to_idx)

    def get_rep(self, data):
        # TODO here add fusion Plugin.
        utterance_rep = self.fusion(data["text_tensor"].permute(1,0,2).contiguous(), data["video_tensor"].permute(1,0,2).contiguous(), data["audio_tensor"].permute(1,0,2).contiguous()).permute(1,0,2).contiguous()
        # print(data["text_tensor"].shape, data["video_tensor"].shape, data["audio_tensor"].shape)
        # print(utterance_rep.shape)
        # exit()

        node_features = self.rnn(data["text_len_tensor"].cpu(), utterance_rep) # [batch_size, mx_len, D_g]
        features, edge_index, edge_norm, edge_type, edge_index_lengths = batch_graphify(
            node_features, data["text_len_tensor"], data["speaker_tensor"], self.wp, self.wf,
            self.edge_type_to_idx, self.edge_att, self.device)

        graph_out = self.gcn(features, edge_index, edge_norm, edge_type)

        return graph_out, features

    def forward(self, data):
        # print(data["text_tensor"].shape, data["video_tensor"].shape, data["audio_tensor"].shape)
        # exit()
        graph_out, features = self.get_rep(data)
        out = self.clf(torch.cat([features, graph_out], dim=-1), data["text_len_tensor"])

        return out

    def get_loss(self, data):
        graph_out, features = self.get_rep(data)
        loss = self.clf.get_loss(torch.cat([features, graph_out], dim=-1),
                                 data["label_tensor"], data["text_len_tensor"])

        return loss
