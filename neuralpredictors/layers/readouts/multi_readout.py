import torch
from .base import *
from .point_pooled import *
from .gaussian import *
from .factorized import *
from .attention import *
from .pyramid import *


class MultiReadoutBase(torch.nn.ModuleDict):
    """
    Base class for MultiReadouts. It is a dictionary of data keys and readouts to the corresponding datasets.
    If parameter-sharing between the readouts is desired, refer to MultiReadoutSharedParametersBase.

    Args:
        in_shape_dict (dict): dictionary of data_key and the corresponding dataset's shape as an output of the core.
        n_neurons_dict (dict): dictionary of data_key and the corresponding dataset's number of neurons
        base_readout (torch.nn.Module): base readout class. If None, self._base_readout must be set manually in the inheriting class's definition
        mean_activity_dict (dict): dictionary of data_key and the corresponding dataset's mean responses. Used to initialize the readout bias with.
                                   If None, the bias is initialized with 0.
        clone_readout (bool): whether to clone the first data_key's readout to all other readouts, only allowing for a scale and offset.
                              This is a rather simple method to enforce parameter-sharing between readouts. For more sophisticated methods,
                              refer to MultiReadoutSharedParametersBase
        gamma_readout (float): regularization strength
        **kwargs:
    """

    _base_readout = None

    def __init__(
        self,
        in_shape_dict,
        n_neurons_dict,
        base_readout=None,
        mean_activity_dict=None,
        clone_readout=False,
        gamma_readout=1.0,
        **kwargs
    ):

        # The `base_readout` can be overridden only if the static property `_base_readout` is not set
        if self._base_readout is None:
            self._base_readout = base_readout

        if self._base_readout is None:
            raise ValueError("Attribute _base_readout must be set")
        super().__init__()

        for i, data_key in enumerate(n_neurons_dict):
            first_data_key = data_key if i == 0 else first_data_key
            mean_activity = mean_activity_dict[data_key] if mean_activity_dict is not None else None

            readout_kwargs = self.prepare_readout_kwargs(i, data_key, first_data_key, **kwargs)

            if i == 0 or clone_readout is False:
                self.add_module(
                    data_key,
                    self._base_readout(
                        in_shape=in_shape_dict[data_key],
                        outdims=n_neurons_dict[data_key],
                        mean_activity=mean_activity,
                        reg_weight=gamma_readout,
                        **readout_kwargs
                    ),
                )
                original_readout = data_key
            elif i > 0 and clone_readout is True:
                self.add_module(data_key, ClonedReadout(self[original_readout]))

        self.initialize(mean_activity_dict)

    def prepare_readout_kwargs(self, i, data_key, first_data_key, **kwargs):
        return kwargs

    def forward(self, *args, data_key=None, **kwargs):
        if data_key is None and len(self) == 1:
            data_key = list(self.keys())[0]
        return self[data_key](*args, **kwargs)

    def initialize(self, mean_activity_dict=None):
        for data_key, readout in self.values():
            mean_activity = mean_activity_dict[data_key] if mean_activity_dict is not None else None
            readout.initialize(mean_activity)

    def regularizer(self, data_key=None, reduction="sum", average=None):
        if data_key is None and len(self) == 1:
            data_key = list(self.keys())[0]
        return self[data_key].regularizer(reduction=reduction, average=average)


class MultiReadoutSharedParametersBase(MultiReadoutBase):
    """
    Base class for MultiReadouts that share parameters between readouts.
    For more information on which parameters can be shared, refer for example to the FullGaussian2d readout
    """
    def prepare_readout_kwargs(self, i, data_key, first_data_key, **kwargs):
        readout_kwargs = kwargs.copy()

        if "grid_mean_predictor" in readout_kwargs:
            if readout_kwargs["grid_mean_predictor"] is not None:
                if readout_kwargs["grid_mean_predictor_type"] == "cortex":
                    readout_kwargs["source_grid"] = readout_kwargs["source_grids"][data_key]
                else:
                    raise KeyError(
                        "grid mean predictor {} does not exist".format(readout_kwargs["grid_mean_predictor_type"])
                    )
                if readout_kwargs["share_transform"]:
                    readout_kwargs["shared_transform"] = None if i == 0 else self[first_data_key].mu_transform

            elif readout_kwargs["share_grid"]:
                readout_kwargs["shared_grid"] = {
                    "match_ids": readout_kwargs["shared_match_ids"][data_key],
                    "shared_grid": None if i == 0 else self[first_data_key].shared_grid,
                }

            del readout_kwargs["share_transform"]
            del readout_kwargs["share_grid"]
            del readout_kwargs["grid_mean_predictor_type"]

        if "share_features" in readout_kwargs:
            if readout_kwargs["share_features"]:
                readout_kwargs["shared_features"] = {
                    "match_ids": readout_kwargs["shared_match_ids"][data_key],
                    "shared_features": None if i == 0 else self[first_data_key].shared_features,
                }
            else:
                readout_kwargs["shared_features"] = None
            del readout_kwargs["share_features"]
        return readout_kwargs


#### MultiReadouts for backwards compatibility
class MultiplePointPooled2d(MultiReadoutBase):
    _base_readout = PointPooled2d

class MultipleSpatialXFeatureLinear(MultiReadoutBase):
    _base_readout = SpatialXFeatureLinear

class MultipleFullSXF(MultiReadoutSharedParametersBase):
    _base_readout = FullSXF

class MultipleFullGaussian2d(MultiReadoutSharedParametersBase):
    _base_readout = FullGaussian2d
