#-----------------------------------------------------------------------------
# Purpose:
#
# Author: Fabio Stefanini
#
# Copyright : University of Zurich, Giacomo Indiveri, Emre Neftci, Sadique Sheik, Fabio Stefanini
# Licence : GPLv2
#-----------------------------------------------------------------------------
import numpy as np
import copy
import itertools as it
from pickle import dump, load

from group import AddrGroup


def _buildGrid(inlist):
    '''
    Builds a multidimensional grid from input lists.
    (tip: operate on indexes, not values)
    Ex:
    >>> _buildGrid([[0,1],[0,2,3]])
    >>> array([[0, 0],
               [0, 2],
               [0, 3],
               [1, 0],
               [1, 2],
               [1, 3]])

    '''
    nD = len(inlist)
    min_list = [0] * nD
    max_list = [None] * nD
    for i in range(nD):
        max_list[i] = len(inlist[i])
    strmgrid = 'np.mgrid['
    for fieldIdx in xrange(nD):
        strmgrid = strmgrid + '{0}:{1},'.format(
            min_list[fieldIdx], max_list[fieldIdx])
    strmgrid = strmgrid + ']'
    allpo = eval(strmgrid)
    tot = np.prod(allpo[0].shape)
    grid = np.zeros([tot, len(allpo)], dtype=type(min_list[0]))
    grid_values = np.zeros_like(grid)
    for j in range(len(allpo)):
        grid[:, j] = allpo[j].flatten()
    for i in range(nD):
        grid_values[:, i] = np.array(inlist[i])[grid[:, i]]
    return grid_values


# TODO: Population.soma[0] should give the (Human) address
class Population(object):
    """
    Population is a set of neurons and corresponding synapses. Population can have parameters
    (efficacy of excitatory input synapses, ...).
    This is on top of synapses and is intended to be used by the user to create neural networks.
    """
    # TODO: extend to multiple chips
    # TODO: proper pickling

    def __init__(self, name, description,
                 setup=None, chipid=None, neurontype=None):
        """
        Init a population by name and description. Population is empty.
        Name and description are used in the graph representation for
        connectivity.
        - name: string
        - description: string
        - setup: NeuroSetup to init the population
        - chipid: string id of the chip in the setup, e.g. 'ifslwta'
        - neurontype: neurontype string to init the population, e.g. 'pixel'
        """
        self.name = name
        self.description = description
        self.soma = AddrGroup('Empty group.')
        self.synapses = dict()
        self.setup = None
        self.neuronblock = None
        if setup is not None and chipid is not None and neurontype is not None:
            self.__populate_init__(setup, chipid, neurontype)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value
        if hasattr(self, 'soma'):
            self.soma.name = self._name + ' ' + 'soma'

        if hasattr(self, 'neuronblock'):
            for s in self.neuronblock.synapses.keys():
                self.synapses[self.neuronblock.synapses[s].
                    id].name = self._name + ' ' + str(s)

    def __copy__(self):
        '''
        Return an exact copy of the population.
        '''
        p = Population(self.name, self.description)
        p.soma = copy.deepcopy(self.soma)
        p.synapses = copy.deepcopy(self.synapses)
        p.setup = self.setup
        p.neuronblock = self.neuronblock
        return p

    def __getitem__(self, i):
        """
        x.__getitem__(i) ==> x[i]
        """
        p = Population(self.name, self.description)
        p.setup = self.setup
        p.neuronblock = self.neuronblock

        if isinstance(i, slice):
            p.soma = self.soma[i]
            p.__populate_synapses__()
            return p
        else:
            p.soma = self.soma[i:i + 1]
            p.__populate_synapses__()
            return p

    def __getslice__(self, i, j):
        """
        x.__getslice__(i, j) ==> x[i:j]
        """
        p = Population(self.name, self.description)
        p.setup = self.setup
        p.neuronblock = self.neuronblock
        p.soma = self.soma[i:j]
        p.__populate_synapses__()
        return p

    def __len__(self):
        """
        len(x) <==> len(x.soma)

        Return the number of neurons in the population.
        """
        return len(self.soma)

    def clear(self):
        """
        Clear the population back to its original state.
        """
        self.soma = AddrGroup('Empty group')
        self.synapses = dict()

    def __populateByExplicitAddr__(self, chipid, addr):
        """
        This function is useful if you know the addresses of neurons and
        synapses. Needs consistence between chipid and addr.
        WARNING: you are supposed to use higher level functions, so use this at
        your own risk!
        """
        raise NotImplementedError

    def isinit(self):
        """
        Return True if population is initiated with setup, chipid and
        neurontype, e.g. not populated.
        """
        if self.setup is None or self.neuronblock is None:
            return False
        else:
            return True

    def union(self, population):
        """
        Add the given population's addresses to the existing one. If the
        address is already there, it doesn't add.
        """
        if not population.isinit():
            # if the other population is still not initiated init with the same
            # parameters of self population but don't populate
            population.init(self.setup, self.soma.chipid, self.neuronblock.id)
        if population.neuronblock.neurochip.id\
           != self.neuronblock.neurochip.id:
                raise Exception(
                    'Union between different chips is not yet implemented.')
        # TODO: actually, addr should be constructed with the appropriate
        # dimensions

        if len(self.soma.addr) != 0 and len(population.soma.addr) != 0:
            self.soma.addr = np.row_stack([self.soma.addr,
                                           population.soma.addr])
        else:  # self.soma is empty
            self.soma.addr = population.soma.addr.copy()

        self.soma.repopulate(self.setup)

        # At this point the order of the addresses is dictated by the order by
        # which they have been added
        # Also, synapses order may also be broken, consider adding
        # __populate_synapses__() here (too slow)
        self.soma.sort()

        return

    def add(self, addresses):
        """
        Adds a neuron (with all its synapses) to the population. Population has to
        be populated already. Address has to be of the appropriate format for
        the chip on which the population has been allocated.
        Arguments are:
            - addresses: neuron address in human format (e.g. [10, 2] for neuron
              [10,2] in a 2D chip.
        """

        for a in addresses:
            if not a in self.neuronblock.soma.addresses:
                raise Exception("At least one address is not present in the population neuronblock.")

        # add soma address(es)
        self.soma.add(self.setup, addresses)
        # add synapses
        for k in self.synapses.keys():
            ch = self.synapses[k].channel
            self.synapses[k].add(
                    self.setup,
                    self.__soma2syn__(addresses, synapses=[k]))
        #self.__unique_addresses__()

    def remove(self, address):
        """
        Removes a neuron (with all its synapses) from the population.
        Arguments are:
            - address: neuron address in human format (e.g. [10, 2] for neuron
              [10,2] in a 2D chip.
        """
        # self.soma.remove([address])...
        raise NotImplementedError

    def __getstate__(self):
        """
        Implement pickling functionalities when dumping.
        """
        d = dict(self.__dict__)
        d['neurontype'] = self.neuronblock.id
        del d['neuronblock']  # don't need to dump neuronblock
        return d

    def __setstate__(self, dict):
        """
        Implement pickling functionalities when loading.
        """
        # TODO: can we do this with __getinitargs__ instead?
        self.__dict__ = copy.copy(dict)
        chip = dict['setup'].chips[dict['soma'].chipid]
        neuronblock = chip.neuron[dict['neurontype']]
        self.neuronblock = neuronblock
        del self.neurontype

    def __soma2syn__(self, addresses, synapses=None):
        """
        Given the neurons addresses, returns all the addresses of its synapses.
        Useful for populating by giving only the soma addresses.
        If synapses is set, returns only those synapses (e.g., 'excitatory0').
        """

        # Freshly generate addresses of synapses
        somaddr = addresses
        nd = len(addresses.dtype)
        synaddr = []

        for s in synapses:
            # Synapses can be multi-dimensional
            syn_block = self.neuronblock.synapses[s]

            # The following codes insures that the addresses are built it the
            # correct order
            ch = self.synapses[s].channel
            ch_ad = self.synapses[s].ch_addr[ch]
            snr = []
            # assumes human readable addresses are of the form neuron -
            # synapse. (could be anything)
            for field in ch_ad.addrConf:
                if field['type'] == -1:
                    if field['id'] in syn_block.dims:
                        snr.append(syn_block.dims[field['id']])
                    else:
                        snr.append([field['default_value']])
            print snr
            #The following three lines are a little intricate.
            #It first builds a grid of possible synapses (see _buildGrid)
            # Then combines it (column_stack) with all possible soma addresses
            # (which is already a grid)
            # Repeat and Tile make sure that the dimenstionalities are
            # consistent
            #and that all possible addresses are considered

            syngrid = _buildGrid(snr)
            pa = self.soma.addr
            somasyngrid = np.column_stack(
                    [np.repeat(pa, len(syngrid), axis=0),
                     np.tile(syngrid.T, len(pa)).T])
            synaddr.append(somasyngrid)

        saddrout = np.array(_flatten(synaddr)).reshape((-1, nd + len(snr)))

        return _sort_by_logical(saddrout)

    def __populate_init__(self, setup, chipid, neurontype):
        """
        Basic operations common to every populate method.
        """
        self.setup = setup

        chip = setup.chips[chipid]

        # check whether neuron is available in the chip
        try:
            neuronblock = chip.neuron[neurontype]
        except KeyError:
            print 'ERROR: %s: No such neurontype in current setup.' %\
                neurontype
            raise Exception('ERROR: Population has not been populated.')

        self.neuronblock = neuronblock  # neuronblock contains translations
                                       # for somas AND synapses biases

        self.soma.__populate__(setup, chipid, 'out')
        self.soma.name = self.name + ' ' + 'soma'

    def init(self, setup, chipid, neurontype):
        """
        self.init ==> self.__populate_init__
        """
        return self.__populate_init__(setup, chipid, neurontype)

    def __populate_synapses__(self):
        """
        Populate all the synapses of the population with the corresponding
        addresses for the neurons in the population.
        """
        self.soma.sort() #sadique: is this necessary ??
        for s in self.neuronblock.synapses.keys():
            syn_id = self.neuronblock.synapses[s].id
            self.synapses[syn_id] = S = AddrGroup(self.
                neuronblock.synapses[s].id)
            self.synapses[syn_id].name = self.name + ' ' + str(s)

            #Populate empty first to set channel and ch_addr of S
            #Consider doing this in AddrGroup
            S.populate_line(self.setup,
                    self.soma.chipid,
                    grouptype='in',
                    addresses=[])

            S.populate_line(self.setup,
                    self.soma.chipid,
                    grouptype='in',
                    addresses=self.__soma2syn__(self.soma.addr, [s]))

    def populate_all(self, setup, chipid, neurontype):
        """
        Populate all the neurons in the given chip.
        """
        self.__populate_init__(setup, chipid, neurontype)

        # filter addresses from the ones available in neuronblock
        addresses = self.neuronblock.soma.addresses
        self.soma.populate_line(setup, chipid, grouptype='out',
                                addresses=addresses)

        self.__populate_synapses__()

    def populate_by_number(self, setup, chipid, neurontype, n, offset=0):
        """
        Takes the given number of addresses from the neuronblock available
        addresses. It takes the first n addresses if offset is not set. Arguments
        are:
            - setup: a NeuroSetup
            - chipid: id of the chip as expressed in setup.xml
            - neurontype: id of neurons as expressed in chipfile.xml (e.g.
            'excitatory')
            - n: the number of neuron to allocate
            - offset: imposes not to take the first addresses
        """

        self.__populate_init__(setup, chipid, neurontype)

        # filter addresses from the ones available in neuronblock
        addresses = self.neuronblock.soma.addresses[offset:n + offset]
        if len(addresses) != n:
            raise Exception("Not enough neurons of this type.")
        self.soma.populate_line(setup, chipid, grouptype='out',
                                addresses=addresses)

        self.__populate_synapses__()

    def populate_sparse(self, setup, chipid, neurontype, p=.3):
        """
        Populate picking random addresses from the neuronblock of all possible
        addresses with probability p. Arguments are:
            - setup: a NeuroSetup
            - chipid: id of the chip as expressed in setup.xml
            - neurontype: id of neurons as expressed in chipfile.xml (e.g.
            'excitatory')
            - p: probability of picking neurons in [0, 1)
        """

        self.__populate_init__(setup, chipid, neurontype)

        # filter addresses from the ones available in neuronblock
        a = np.array(self.neuronblock.soma.addresses)
        addresses = a[np.random.random(len(a)) < p]

        self.soma.populate_line(setup, chipid, grouptype='out',
                                addresses=addresses)

        self.__populate_synapses__()

    def populate_by_topology(self, setup, chipid, neurontype, topology='rectangle', topology_kwargs={'p1': [0, 0], 'p2': [63, 0]}):
        """
        Takes the given number of addresses by respecting the chips natural topology (i.e. 0 to n%X+n/Y). It takes the first n addresses if offset is not set. Arguments
        are:
            - setup: a NeuroSetup
            - neurontype: id of neurons as expressed in chipfile.xml (e.g.
            'excitatory')
            - n: the number of neuron to allocate
        """

        self.__populate_init__(setup, chipid, neurontype)

        # all the addresses for the given topology
        S = AddrGroup(self.neuronblock.soma.id)
        getattr(S, 'populate_' + topology)(setup, chipid,
             grouptype='out', **topology_kwargs)
        addresses = _set_intersection(S.addr, self.neuronblock.soma.addresses)
        self.soma.populate_line(
            setup, chipid, grouptype='out', addresses=addresses)
        self.__populate_synapses__()

    def populate_by_id(self, setup, chipid, neurontype, id_list, axes=0):
        """
        Takes the given addresses (as list) from the neuronblock available
        addresses. It takes the first n addresses if offset is not set.
        Arguments are:
            - setup: a NeuroSetup
            - chipid: id of the chip as expressed in setup.xml
            - neurontype: id of neurons as expressed in chipfile.xml (e.g.
            'excitatory')
            - id_list: the list of ids for neurons to allocate (human addresses)
            - axes: chosse the axes by which to filter the addresses
        """

        self.__populate_init__(setup, chipid, neurontype)

        # filter addresses
        addresses = []
        for t in self.neuronblock.soma.addresses:
            if int(t[axes]) in id_list:
                addresses.append(t)
        try:
            self.soma.populate_line(
                setup, chipid, grouptype='out', addresses=addresses)
        except:
            raise Exception, "Chip %s contains no neurons of given id_list on axes %d." % (
                chipid, axes)

        self.__populate_synapses__()


def _set_intersection(A, B):
    """
    returns elements that are both in A and B
    Does NOT recover original order!!! Instead sorts according to the same order as logical addresses
    """
    A = set(tuple(i) for i in A)
    B = set(tuple(i) for i in B)
    AinterB = np.array(list(A.intersection(B)), 'int')
    #Importing from unordered list: must sort back to initial order
    # zip(*a[::-1]) because we want to sort with respect to rightmost column
    # (this is how pyST builds it)
    #AinterB=AinterB[np.lexsort(zip(*AinterB[:,::-1]))]
    return _sort_by_logical(AinterB)


def _sort_by_logical(S):
    """
    Sort in-place according to the logical addesses order
    """
    return S[np.lexsort(zip(*S[:, :]))]


def _sort_by_antilogical(S):
    """
    Sort in-place according to the logical addesses order
    """
    return S[np.lexsort(zip(*S[:, ::-1]))]


def _flatten(l, ltypes=(list, tuple, np.ndarray)):
    '''
    The function flattens lists of lists or tuples or ints
    Taken from web
    http://rightfootin.blogspot.com/2006/09/more-on-python-flatten.html
    '''
    ltype = type(l)
    l = list(l)
    i = 0
    while i < len(l):
        while isinstance(l[i], ltypes):
            # The commented code is supposed to eliminate blank ararys
            # But has a bug and also eliminates zeros
            #if not l[i] and l[i]!=0:
            #    l.pop(i)
            #    i -= 1
            #    break
            #else:
            l[i:i + 1] = l[i]
        i += 1
    return ltype(l)