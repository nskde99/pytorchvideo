# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved.

from typing import List, Optional

import torch
import torch.nn as nn
from pytorchvideo.layers.utils import set_attributes
from pytorchvideo.models.weight_init import init_net_weights


class Net(nn.Module):
    """
    Build a general Net models with a list of blocks for video recognition.

    ::

                                         Input
                                           ↓
                                         Block 1
                                           ↓
                                           .
                                           .
                                           .
                                           ↓
                                         Block N
                                           ↓

    The ResNet builder can be found in `create_resnet`.
    """

    def __init__(self, *, blocks: nn.ModuleList) -> None:
        """
        Args:
            blocks (torch.nn.module_list): the list of block modules.
        """
        super().__init__()
        assert blocks is not None
        self.blocks = blocks
        init_net_weights(self)

    # @torch.jit.script_method                     # Need to comment this to trace model successfully
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        for idx in range(len(self.blocks)):
            x = self.blocks[idx](x)
        return x


class DetectionBBoxNetwork(nn.Module):
    """
    A general purpose model that handles bounding boxes as part of input.
    """

    def __init__(self, model: nn.Module, detection_head: nn.Module):
        """
        Args:
            model (nn.Module): a model that preceeds the head. Ex: stem + stages.
            detection_head (nn.Module): a network head. that can take in input bounding boxes
                and the outputs from the model.
        """
        super().__init__()
        self.model = model
        self.detection_head = detection_head

    def forward(self, x: torch.Tensor, bboxes: torch.Tensor):
        """
        Args:
            x (torch.tensor): input tensor
            bboxes (torch.tensor): accociated bounding boxes.
                The format is N*5 (Index, X_1,Y_1,X_2,Y_2) if using RoIAlign
                and N*6 (Index, x_ctr, y_ctr, width, height, angle_degrees) if
                using RoIAlignRotated.
        """
        features = self.model(x)
        out = self.detection_head(features, bboxes)
        return out.view(out.shape[0], -1)


class MultiPathWayWithFuse(nn.Module):
    """
    Build multi-pathway block with fusion for video recognition, each of the pathway
    contains its own Blocks and Fusion layers across different pathways.

    ::

                            Pathway 1  ... Pathway N
                                ↓              ↓
                             Block 1        Block N
                                ↓⭠ --Fusion----↓
    """

    def __init__(
        self,
        *,
        multipathway_blocks: nn.ModuleList,
        multipathway_fusion: Optional[nn.Module],
        inplace: Optional[bool] = True,
    ) -> None:
        """
        Args:
            multipathway_blocks (nn.module_list): list of models from all pathways.
            multipathway_fusion (nn.module): fusion model.
            inplace (bool): If inplace, directly update the input list without making
                a copy.
        """
        super().__init__()
        set_attributes(self, locals())

    def forward(self, x: List[torch.Tensor]) -> torch.Tensor:
        assert isinstance(
            x, list
        ), "input for MultiPathWayWithFuse needs to be a list of tensors"
        if self.inplace:
            x_out = x
        else:
            x_out = [None] * len(x)
        for pathway_idx in range(len(self.multipathway_blocks)):
            if self.multipathway_blocks[pathway_idx] is not None:
                x_out[pathway_idx] = self.multipathway_blocks[pathway_idx](
                    x[pathway_idx]
                )
        if self.multipathway_fusion is not None:
            x_out = self.multipathway_fusion(x_out)
        return x_out
