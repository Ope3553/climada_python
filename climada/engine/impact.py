"""
Define Impact and ImpactFreqCurve classes.
"""

__all__ = ['ImpactFreqCurve', 'Impact']

import os
import logging
import numpy as np

from climada.entity.tag import Tag
from climada.hazard.tag import Tag as TagHazard
from climada.util.coordinates import Coordinates
import climada.util.plot as plot

LOGGER = logging.getLogger(__name__)

class ImpactFreqCurve(object):
    """ Impact exceedence frequency curve.

    Attributes:
        return_per (np.array): return period
        impact (np.array): impact exceeding frequency
        unit (str): value unit used (given by exposures unit)
        label (str): string describing source data
    """
    def __init__(self):
        self.return_per = np.array([])
        self.impact = np.array([])
        self.unit = 'NA'
        self.label = ''

    def plot(self):
        """Plot impact frequency curve.

        Returns:
            matplotlib.figure.Figure, [matplotlib.axes._subplots.AxesSubplot]
        """
        graph = plot.Graph2D(self.label)
        graph.add_subplot('Return period (year)', 'Impact (%s)' % self.unit)
        graph.add_curve(self.return_per, self.impact, 'y')
        return graph.get_elems()

    def plot_compare(self, ifc):
        """Plot current and input impact frequency curves in a figure.

        Returns:
            matplotlib.figure.Figure, [matplotlib.axes._subplots.AxesSubplot]
        """
        if self.unit != ifc.unit:
            LOGGER.warning("Comparing between two different units: %s and %s",\
                         self.unit, ifc.unit)
        graph = plot.Graph2D('', 2)
        graph.add_subplot('Return period (year)', 'Impact (%s)' % self.unit)
        graph.add_curve(self.return_per, self.impact, 'b', label=self.label)
        graph.add_curve(ifc.return_per, ifc.impact, 'r', label=ifc.label)
        return graph.get_elems()

class Impact(object):
    """Impact definition. Compute from an entity (exposures and impact
    functions) and hazard.

    Attributes:
        exposures_tag (Tag): information about the exposures
        impact_funcs_tag (Tag): information about the impact functions
        hazard_tag (TagHazard): information about the hazard
        event_id (np.array): id (>0) of each hazard event
        event_name (list): name of each hazard event
        coord_exp (Coordinates): exposures coordinates (in degrees)
        eai_exp (np.array): expected annual impact for each exposure
        at_event (np.array): impact for each hazard event
        frequency (np.arrray): annual frequency of event
        tot_value (float): total exposure value affected
        aai_agg (float): average annual impact (aggregated)
        unit (str): value unit used (given by exposures unit)
    """

    def __init__(self):
        """ Empty initialization."""
        self.exposures_tag = Tag()
        self.impact_funcs_tag = Tag()
        self.hazard_tag = TagHazard()
        self.event_id = np.array([], int)
        self.event_name = list()
        self.date = np.array([], int)
        self.coord_exp = Coordinates()
        self.eai_exp = np.array([])
        self.at_event = np.array([])
        self.frequency = np.array([])
        self.tot_value = 0
        self.aai_agg = 0
        self.unit = 'NA'

    def calc_freq_curve(self):
        """Compute impact exceedance frequency curve.

        Returns:
            ImpactFreqCurve
        """
        ifc = ImpactFreqCurve()
        # Sort descendingly the impacts per events
        sort_idxs = np.argsort(self.at_event)[::-1]
        # Calculate exceedence frequency
        exceed_freq = np.cumsum(self.frequency[sort_idxs])
        # Set return period and imact exceeding frequency
        ifc.return_per = 1/exceed_freq
        ifc.impact = self.at_event[sort_idxs]
        ifc.unit = self.unit
        ifc.label = os.path.splitext(os.path.basename( \
            self.exposures_tag.file_name))[0] + ' x ' + \
            os.path.splitext(os.path.basename(self.hazard_tag.file_name))[0]
        return ifc

    def calc(self, exposures, impact_funcs, hazard):
        """Compute impact of an hazard to exposures.

        Parameters:
            exposures (Exposures): exposures
            impact_funcs (ImpactFuncSet): impact functions
            hazard (Hazard): hazard

        Examples:
            Use Entity class:

            >>> hazard = Hazard(HAZ_DEMO_MAT) # Set hazard
            >>> entity = Entity() # Load entity with default values
            >>> entity.exposures = Exposures(ENT_TEMPLATE_XLS) # Set exposures
            >>> tc_impact = Impact()
            >>> tc_impact.calc(entity.exposures, entity.impact_functs, hazard)

            Specify only exposures and impact functions:

            >>> hazard = Hazard(HAZ_DEMO_MAT) # Set hazard
            >>> funcs = ImpactFuncSet(ENT_TEMPLATE_XLS) # Set impact functions
            >>> exposures = Exposures(ENT_TEMPLATE_XLS) # Set exposures
            >>> tc_impact = Impact()
            >>> tc_impact.calc(exposures, funcs, hazard)
        """
        # 1. Assign centroids to each exposure if not done
        if (not exposures.assigned) or \
        (hazard.tag.haz_type not in exposures.assigned):
            exposures.assign(hazard)

        # 2. Initialize values
        self.unit = exposures.value_unit
        self.event_id = hazard.event_id
        self.event_name = hazard.event_name
        self.date = hazard.date
        self.coord_exp = exposures.coord
        self.frequency = hazard.frequency
        self.at_event = np.zeros(hazard.intensity.shape[0])
        self.eai_exp = np.zeros(len(exposures.value))
        self.tot_value = 0
        self.exposures_tag = exposures.tag
        self.impact_funcs_tag = impact_funcs.tag
        self.hazard_tag = hazard.tag
        # Select exposures with positive value and assigned centroid
        exp_idx = np.where(np.logical_and(exposures.value > 0, \
                           exposures.assigned[hazard.tag.haz_type] >= 0))[0]
        # Warning if no exposures selected
        if exp_idx.size == 0:
            LOGGER.warning("No affected exposures.")
            return
        LOGGER.info('Calculating damage for %s assets (>0) and %s events.',
                    exp_idx.size, hazard.event_id.size)

        # Get hazard type
        haz_type = hazard.tag.haz_type
        # Get damage functions for this hazard
        haz_imp = impact_funcs.get_func(haz_type)

        # 3. Loop over exposures according to their impact function
        # Loop over impact functions
        for imp_fun in haz_imp:
            # get indices of all the exposures with this impact function
            exp_iimp = np.where(exposures.impact_id[exp_idx] == imp_fun.id)[0]

            # loop over selected exposures
            for iexp in exp_idx[exp_iimp]:
                # compute impact on exposure
                event_row, impact = self._one_exposure(iexp, exposures, \
                                                        hazard, imp_fun)

                # add values to impact impact
                self.at_event[event_row] += impact
                self.eai_exp[iexp] += np.squeeze(sum(impact * hazard. \
                           frequency[event_row]))
                self.tot_value += exposures.value[iexp]

        self.aai_agg = sum(self.at_event * hazard.frequency)

    def plot_eai_exposure(self, ignore_null=True, **kwargs):
        """Plot expected annual impact of each exposure.

        Parameters:
            ignore_null (bool): ignore zero impact values at exposures
            kwargs (optional): arguments for hexbin matplotlib function

         Returns:
            matplotlib.figure.Figure, cartopy.mpl.geoaxes.GeoAxesSubplot
        """
        title = 'Expected annual impact'
        col_name = 'Impact ' + self.unit
        if ignore_null:
            pos_vals = self.eai_exp > 0
        else:
            pos_vals = np.ones((self.eai_exp.size,), dtype=bool)
        if 'reduce_C_function' not in kwargs:
            kwargs['reduce_C_function'] = np.sum
        return plot.geo_bin_from_array(self.eai_exp[pos_vals], \
            self.coord_exp[pos_vals], col_name, title, **kwargs)

    @staticmethod
    def _one_exposure(iexp, exposures, hazard, imp_fun):
        """Impact to one exposures.

        Parameters:
            iexp (int): array index of the exposure computed
            exposures (Exposures): exposures
            hazard (Hazard): a hazard
            imp_fun (ImpactFunc): an impact function

        Returns:
            event_row (np.array): hazard' events indices affecting exposure
            impact (np.array): impact for each event in event_row
        """
        # get assigned centroid of this exposure
        icen = int(exposures.assigned[hazard.tag.haz_type][iexp])

        # get intensities for this centroid
        event_row = hazard.intensity[:, icen].nonzero()[0]
        inten_val = np.asarray(hazard.intensity[event_row, icen].todense()). \
                    squeeze()
        # get affected fraction for these events
        fract = np.squeeze(hazard.fraction[:, icen].toarray()[event_row])

        # impact on this exposure
        impact = exposures.value[iexp] * imp_fun.calc_mdr(inten_val) * fract
        if np.count_nonzero(impact) > 0:
            paa = np.interp(inten_val, imp_fun.intensity, imp_fun.paa)
            # TODO: if needed?
            if (exposures.deductible[iexp] > 0) or \
                (exposures.cover[iexp] < exposures.value[iexp]):
                impact = np.minimum(np.maximum(impact - \
                                               exposures.deductible[iexp] * \
                                               paa, 0), exposures.cover[iexp])
        return event_row, impact
