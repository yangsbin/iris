# (C) British Crown Copyright 2010 - 2019, Met Office
#
# This file is part of Iris.
#
# Iris is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the
# Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Iris is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Iris.  If not, see <http://www.gnu.org/licenses/>.
"""
Test the cube merging mechanism.

"""

from __future__ import (absolute_import, division, print_function)
from six.moves import (filter, input, map, range, zip)  # noqa
import six

# import iris tests first so that some things can be initialised before importing anything else
import iris.tests as tests

from collections import Iterable
import datetime
import itertools
import numpy as np
import numpy.ma as ma

import iris
from iris._lazy_data import as_lazy_data
import iris.cube
from iris.coords import DimCoord, AuxCoord
import iris.exceptions
import iris.tests.stock


class TestMixin(object):
    """
    Mix-in class for attributes & utilities common to these test cases.

    """
    def test_normal_cubes(self):
        cubes = iris.load(self._data_path)
        self.assertEqual(len(cubes), self._num_cubes)
        names = ['forecast_period', 'forecast_reference_time', 'level_height', 'model_level_number', 'sigma', 'source']
        axes = ['forecast_period', 'rt', 'z', 'z', 'z', 'source']
        self.assertCML(cubes, ['merge', self._prefix + '.cml'])

    def test_remerge(self):
        # After the merge process the coordinates within each cube can be in a
        # different order. Until that changes we can't compare the cubes
        # directly or with the CML ... so we just make sure the count stays
        # the same.
        cubes = iris.load(self._data_path)
        cubes2 = cubes.merge()
        self.assertEqual(len(cubes), len(cubes2))

    def test_duplication(self):
        cubes = iris.load(self._data_path)
        self.assertRaises(iris.exceptions.DuplicateDataError, (cubes + cubes).merge)
        cubes2 = (cubes + cubes).merge(unique=False)
        self.assertEqual(len(cubes2), 2 * len(cubes))


@tests.skip_data
class TestSingleCube(tests.IrisTest, TestMixin):
    def setUp(self):
        self._data_path = tests.get_data_path(('PP', 'globClim1', 'theta.pp'))
        self._num_cubes = 1
        self._prefix = 'theta'


@tests.skip_data
class TestMultiCube(tests.IrisTest, TestMixin):
    def setUp(self):
        self._data_path = tests.get_data_path(('PP', 'globClim1', 'dec_subset.pp'))
        self._num_cubes = 4
        self._prefix = 'dec'

    def test_coord_attributes(self):
        def custom_coord_callback(cube, field, filename):
            cube.coord('time').attributes['monty'] = 'python'
            cube.coord('time').attributes['brain'] = 'hurts'

        # Load slices, decorating a coord with custom attributes
        cubes = iris.load_raw(self._data_path, callback=custom_coord_callback)
        # Merge
        merged = iris.cube.CubeList._extract_and_merge(cubes, constraints=None, strict=False, merge_unique=False)
        # Check the custom attributes are in the merged cube
        for cube in merged:
            assert(cube.coord('time').attributes['monty'] == 'python')
            assert(cube.coord('time').attributes['brain'] == 'hurts')


@tests.skip_data
class TestColpex(tests.IrisTest):
    def setUp(self):
        self._data_path = tests.get_data_path(('PP', 'COLPEX', 'small_colpex_theta_p_alt.pp'))

    def test_colpex(self):
        cubes = iris.load(self._data_path)
        self.assertEqual(len(cubes), 3)
        self.assertCML(cubes, ('COLPEX', 'small_colpex_theta_p_alt.cml'))


class TestDataMergeCombos(tests.IrisTest):
    def _make_data(self, data, dtype=np.dtype('int32'), fill_value=None,
                   mask=None, lazy=False, N=3):
        if isinstance(data, Iterable):
            shape = (len(data), N, N)
            data = np.array(data).reshape(-1, 1, 1)
        else:
            shape = (N, N)
        if mask is not None:
            payload = ma.empty(shape, dtype=dtype, fill_value=fill_value)
            payload.data[:] = data
            if isinstance(mask, bool):
                payload.mask = mask
            else:
                payload[mask] = ma.masked
        else:
            payload = np.empty(shape, dtype=dtype)
            payload[:] = data
        if lazy:
            payload = as_lazy_data(payload)
        return payload

    def _make_cube(self, data, dtype=np.dtype('int32'), fill_value=None,
                   mask=None, lazy=False, N=3):
        x = np.arange(N)
        y = np.arange(N)
        payload = self._make_data(data, dtype=dtype, fill_value=fill_value,
                                  mask=mask, lazy=lazy, N=N)
        cube = iris.cube.Cube(payload)
        lat = DimCoord(y, standard_name='latitude', units='degrees')
        cube.add_dim_coord(lat, 0)
        lon = DimCoord(x, standard_name='longitude', units='degrees')
        cube.add_dim_coord(lon, 1)
        height = DimCoord(data, standard_name='height', units='m')
        cube.add_aux_coord(height)
        return cube

    @staticmethod
    def _expected_fill_value(fill0='none', fill1='none'):
        result = None
        if fill0 != 'none' or fill1 != 'none':
            if fill0 == 'none':
                result = fill1
            elif fill1 == 'none':
                result = fill0
            elif fill0 == fill1:
                result = fill0
        return result

    def _check_fill_value(self, result, fill0='none', fill1='none'):
        expected_fill_value = self._expected_fill_value(fill0, fill1)
        if expected_fill_value is None:
            data = result.data
            if ma.isMaskedArray(data):
                np_fill_value = ma.masked_array(0,
                                                dtype=result.dtype).fill_value
                self.assertEqual(data.fill_value, np_fill_value)
        else:
            data = result.data
            if ma.isMaskedArray(data):
                self.assertEqual(data.fill_value, expected_fill_value)

    def setUp(self):
        self.dtype = np.dtype('int32')
        fill_value = 1234
        self.lazy_combos = itertools.product([False, True],
                                             [False, True])
        fill_combos = itertools.product([None, fill_value],
                                        [fill_value, None])
        single_fill_combos = itertools.product([None, fill_value])
        self.combos = itertools.product(self.lazy_combos, fill_combos)
        self.mixed_combos = itertools.product(self.lazy_combos,
                                              single_fill_combos)

    def test__ndarray_ndarray(self):
        for (lazy0, lazy1) in self.lazy_combos:
            cubes = iris.cube.CubeList()
            cubes.append(self._make_cube(0, dtype=self.dtype, lazy=lazy0))
            cubes.append(self._make_cube(1, dtype=self.dtype, lazy=lazy1))
            result = cubes.merge_cube()
            expected = self._make_data([0, 1], dtype=self.dtype)
            self.assertArrayEqual(result.data, expected)
            self.assertEqual(result.dtype, self.dtype)
            self._check_fill_value(result)

    def test__masked_masked(self):
        for (lazy0, lazy1), (fill0, fill1) in self.combos:
            cubes = iris.cube.CubeList()
            mask = [(0,), (0,)]
            cubes.append(self._make_cube(0, mask=mask, lazy=lazy0,
                                         dtype=self.dtype,
                                         fill_value=fill0))
            mask = [(1,), (1,)]
            cubes.append(self._make_cube(1, mask=mask, lazy=lazy1,
                                         dtype=self.dtype,
                                         fill_value=fill1))
            result = cubes.merge_cube()
            mask = [(0, 1), (0, 1), (0, 1)]
            expected_fill_value = self._expected_fill_value(fill0, fill1)
            expected = self._make_data([0, 1], mask=mask, dtype=self.dtype,
                                       fill_value=expected_fill_value)
            self.assertMaskedArrayEqual(result.data, expected)
            self.assertEqual(result.dtype, self.dtype)
            self._check_fill_value(result, fill0, fill1)

    def test__ndarray_masked(self):
        for (lazy0, lazy1), (fill,) in self.mixed_combos:
            cubes = iris.cube.CubeList()
            cubes.append(self._make_cube(0, lazy=lazy0, dtype=self.dtype))
            mask = [(0, 1), (0, 1)]
            cubes.append(self._make_cube(1, mask=mask, lazy=lazy1,
                                         dtype=self.dtype,
                                         fill_value=fill))
            result = cubes.merge_cube()
            mask = [(1, 1), (0, 1), (0, 1)]
            expected_fill_value = self._expected_fill_value(fill)
            expected = self._make_data([0, 1], mask=mask, dtype=self.dtype,
                                       fill_value=expected_fill_value)
            self.assertMaskedArrayEqual(result.data, expected)
            self.assertEqual(result.dtype, self.dtype)
            self._check_fill_value(result, fill1=fill1)

    def test__masked_ndarray(self):
        for (lazy0, lazy1), (fill,) in self.mixed_combos:
            cubes = iris.cube.CubeList()
            mask = [(0, 1), (0, 1)]
            cubes.append(self._make_cube(0, mask=mask, lazy=lazy0,
                                         dtype=self.dtype,
                                         fill_value=fill))
            cubes.append(self._make_cube(1, lazy=lazy1, dtype=self.dtype))
            result = cubes.merge_cube()
            mask = [(0, 0), (0, 1), (0, 1)]
            expected_fill_value = self._expected_fill_value(fill)
            expected = self._make_data([0, 1], mask=mask, dtype=self.dtype,
                                       fill_value=expected_fill_value)
            self.assertMaskedArrayEqual(result.data, expected)
            self.assertEqual(result.dtype, self.dtype)
            self._check_fill_value(result, fill0=fill)

    def test_maksed_array_preserved(self):
        for (lazy0, lazy1), (fill,) in self.mixed_combos:
            cubes = iris.cube.CubeList()
            mask = False
            cubes.append(self._make_cube(0, mask=mask, lazy=lazy0,
                                         dtype=self.dtype,
                                         fill_value=fill))
            cubes.append(self._make_cube(1, lazy=lazy1, dtype=self.dtype))
            result = cubes.merge_cube()
            mask = False
            expected_fill_value = self._expected_fill_value(fill)
            expected = self._make_data([0, 1], mask=mask, dtype=self.dtype,
                                       fill_value=expected_fill_value)
            self.assertEqual(type(result.data), ma.MaskedArray)
            self.assertMaskedArrayEqual(result.data, expected)
            self.assertEqual(result.dtype, self.dtype)
            self._check_fill_value(result, fill0=fill)

    def test_fill_value_invariant_to_order__same_non_None(self):
        fill_value = 1234
        cubes = [self._make_cube(i, mask=True,
                                 fill_value=fill_value) for i in range(3)]
        for combo in itertools.permutations(cubes):
            result = iris.cube.CubeList(combo).merge_cube()
            self.assertEqual(result.data.fill_value, fill_value)

    def test_fill_value_invariant_to_order__all_None(self):
        cubes = [self._make_cube(i, mask=True,
                                 fill_value=None) for i in range(3)]
        for combo in itertools.permutations(cubes):
            result = iris.cube.CubeList(combo).merge_cube()
            np_fill_value = ma.masked_array(0, dtype=result.dtype).fill_value
            self.assertEqual(result.data.fill_value, np_fill_value)

    def test_fill_value_invariant_to_order__different_non_None(self):
        cubes = [self._make_cube(0, mask=True, fill_value=1234)]
        cubes.append(self._make_cube(1, mask=True, fill_value=2341))
        cubes.append(self._make_cube(2, mask=True, fill_value=3412))
        cubes.append(self._make_cube(3, mask=True, fill_value=4123))
        for combo in itertools.permutations(cubes):
            result = iris.cube.CubeList(combo).merge_cube()
            np_fill_value = ma.masked_array(0, dtype=result.dtype).fill_value
            self.assertEqual(result.data.fill_value, np_fill_value)

    def test_fill_value_invariant_to_order__mixed(self):
        cubes = [self._make_cube(0, mask=True, fill_value=None)]
        cubes.append(self._make_cube(1, mask=True, fill_value=1234))
        cubes.append(self._make_cube(2, mask=True, fill_value=4321))
        for combo in itertools.permutations(cubes):
            result = iris.cube.CubeList(combo).merge_cube()
            np_fill_value = ma.masked_array(0, dtype=result.dtype).fill_value
            self.assertEqual(result.data.fill_value, np_fill_value)


@tests.skip_data
class TestDataMerge(tests.IrisTest):
    def test_extended_proxy_data(self):
        # Get the empty theta cubes for T+1.5 and T+2
        data_path = tests.get_data_path(
            ('PP', 'COLPEX', 'theta_and_orog_subset.pp'))
        phenom_constraint = iris.Constraint('air_potential_temperature')
        datetime_1 = datetime.datetime(2009, 9, 9, 17, 20)
        datetime_2 = datetime.datetime(2009, 9, 9, 17, 50)
        time_constraint1 = iris.Constraint(time=datetime_1)
        time_constraint2 = iris.Constraint(time=datetime_2)
        time_constraint_1_and_2 = iris.Constraint(
            time=lambda c: c in (datetime_1, datetime_2))
        cube1 = iris.load_cube(data_path, phenom_constraint & time_constraint1)
        cube2 = iris.load_cube(data_path, phenom_constraint & time_constraint2)

        # Merge the two halves
        cubes = iris.cube.CubeList([cube1, cube2]).merge(True)
        self.assertCML(cubes, ('merge', 'theta_two_times.cml'))

        # Make sure we get the same result directly from load
        cubes = iris.load_cube(data_path,
            phenom_constraint & time_constraint_1_and_2)
        self.assertCML(cubes, ('merge', 'theta_two_times.cml'))

    def test_real_data(self):
        data_path = tests.get_data_path(('PP', 'globClim1', 'theta.pp'))
        cubes = iris.load_raw(data_path)
        # Force the source 2-D cubes to load their data before the merge
        for cube in cubes:
            data = cube.data
        cubes = cubes.merge()
        self.assertCML(cubes, ['merge', 'theta.cml'])


class TestDimensionSplitting(tests.IrisTest):
    def _make_cube(self, a, b, c, data):
        cube_data = np.empty((4, 5), dtype=np.float32)
        cube_data[:] = data
        cube = iris.cube.Cube(cube_data)
        cube.add_dim_coord(DimCoord(np.array([0, 1, 2, 3, 4], dtype=np.int32), long_name='x', units='1'), 1)
        cube.add_dim_coord(DimCoord(np.array([0, 1, 2, 3], dtype=np.int32), long_name='y', units='1'), 0)
        cube.add_aux_coord(DimCoord(np.array([a], dtype=np.int32), long_name='a', units='1'))
        cube.add_aux_coord(DimCoord(np.array([b], dtype=np.int32), long_name='b', units='1'))
        cube.add_aux_coord(DimCoord(np.array([c], dtype=np.int32), long_name='c', units='1'))
        return cube

    def test_single_split(self):
        # Test what happens when a cube forces a simple, two-way split.
        cubes = []
        cubes.append(self._make_cube(0, 0, 0, 0))
        cubes.append(self._make_cube(0, 1, 1, 1))
        cubes.append(self._make_cube(1, 0, 2, 2))
        cubes.append(self._make_cube(1, 1, 3, 3))
        cubes.append(self._make_cube(2, 0, 4, 4))
        cubes.append(self._make_cube(2, 1, 5, 5))
        cube = iris.cube.CubeList(cubes).merge()
        self.assertCML(cube, ('merge', 'single_split.cml'))

    def test_multi_split(self):
        # Test what happens when a cube forces a three-way split.
        cubes = []
        cubes.append(self._make_cube(0, 0, 0, 0))
        cubes.append(self._make_cube(0, 0, 1, 1))
        cubes.append(self._make_cube(0, 1, 0, 2))
        cubes.append(self._make_cube(0, 1, 1, 3))
        cubes.append(self._make_cube(1, 0, 0, 4))
        cubes.append(self._make_cube(1, 0, 1, 5))
        cubes.append(self._make_cube(1, 1, 0, 6))
        cubes.append(self._make_cube(1, 1, 1, 7))
        cubes.append(self._make_cube(2, 0, 0, 8))
        cubes.append(self._make_cube(2, 0, 1, 9))
        cubes.append(self._make_cube(2, 1, 0, 10))
        cubes.append(self._make_cube(2, 1, 1, 11))
        cube = iris.cube.CubeList(cubes).merge()
        self.assertCML(cube, ('merge', 'multi_split.cml'))


class TestCombination(tests.IrisTest):
    def _make_cube(self, a, b, c, d, data=0):
        cube_data = np.empty((4, 5), dtype=np.float32)
        cube_data[:] = data
        cube = iris.cube.Cube(cube_data)
        cube.add_dim_coord(DimCoord(np.array([0, 1, 2, 3, 4], dtype=np.int32),
                                    long_name='x', units='1'), 1)
        cube.add_dim_coord(DimCoord(np.array([0, 1, 2, 3], dtype=np.int32),
                                    long_name='y', units='1'), 0)

        for name, value in zip(['a', 'b', 'c', 'd'], [a, b, c, d]):
            dtype = np.str if isinstance(value, six.string_types) else np.float32
            cube.add_aux_coord(AuxCoord(np.array([value], dtype=dtype),
                                        long_name=name, units='1'))

        return cube

    def test_separable_combination(self):
        cubes = iris.cube.CubeList()
        cubes.append(self._make_cube('2005', 'ECMWF',
                                     'HOPE-E, Sys 1, Met 1, ENSEMBLES', 0))
        cubes.append(self._make_cube('2005', 'ECMWF',
                                     'HOPE-E, Sys 1, Met 1, ENSEMBLES', 1))
        cubes.append(self._make_cube('2005', 'ECMWF',
                                     'HOPE-E, Sys 1, Met 1, ENSEMBLES', 2))
        cubes.append(self._make_cube('2026', 'UK Met Office',
                                     'HadGEM2, Sys 1, Met 1, ENSEMBLES', 0))
        cubes.append(self._make_cube('2026', 'UK Met Office',
                                     'HadGEM2, Sys 1, Met 1, ENSEMBLES', 1))
        cubes.append(self._make_cube('2026', 'UK Met Office',
                                     'HadGEM2, Sys 1, Met 1, ENSEMBLES', 2))
        cubes.append(self._make_cube('2002', 'CERFACS',
                                     'GELATO, Sys 0, Met 1, ENSEMBLES', 0))
        cubes.append(self._make_cube('2002', 'CERFACS',
                                     'GELATO, Sys 0, Met 1, ENSEMBLES', 1))
        cubes.append(self._make_cube('2002', 'CERFACS',
                                     'GELATO, Sys 0, Met 1, ENSEMBLES', 2))
        cubes.append(self._make_cube('2002', 'IFM-GEOMAR',
                                     'ECHAM5, Sys 1, Met 10, ENSEMBLES', 0))
        cubes.append(self._make_cube('2002', 'IFM-GEOMAR',
                                     'ECHAM5, Sys 1, Met 10, ENSEMBLES', 1))
        cubes.append(self._make_cube('2002', 'IFM-GEOMAR',
                                     'ECHAM5, Sys 1, Met 10, ENSEMBLES', 2))
        cubes.append(self._make_cube('2502', 'UK Met Office',
                                     'HadCM3, Sys 51, Met 10, ENSEMBLES', 0))
        cubes.append(self._make_cube('2502', 'UK Met Office',
                                     'HadCM3, Sys 51, Met 11, ENSEMBLES', 0))
        cubes.append(self._make_cube('2502', 'UK Met Office',
                                     'HadCM3, Sys 51, Met 12, ENSEMBLES', 0))
        cubes.append(self._make_cube('2502', 'UK Met Office',
                                     'HadCM3, Sys 51, Met 13, ENSEMBLES', 0))
        cubes.append(self._make_cube('2502', 'UK Met Office',
                                     'HadCM3, Sys 51, Met 14, ENSEMBLES', 0))
        cubes.append(self._make_cube('2502', 'UK Met Office',
                                     'HadCM3, Sys 51, Met 15, ENSEMBLES', 0))
        cubes.append(self._make_cube('2502', 'UK Met Office',
                                     'HadCM3, Sys 51, Met 16, ENSEMBLES', 0))
        cubes.append(self._make_cube('2502', 'UK Met Office',
                                     'HadCM3, Sys 51, Met 17, ENSEMBLES', 0))
        cubes.append(self._make_cube('2502', 'UK Met Office',
                                     'HadCM3, Sys 51, Met 18, ENSEMBLES', 0))
        cube = cubes.merge()
        self.assertCML(cube, ('merge', 'separable_combination.cml'),
                       checksum=False)


class TestDimSelection(tests.IrisTest):
    def _make_cube(self, a, b, data=0, a_dim=False, b_dim=False):
        cube_data = np.empty((4, 5), dtype=np.float32)
        cube_data[:] = data
        cube = iris.cube.Cube(cube_data)
        cube.add_dim_coord(DimCoord(np.array([0, 1, 2, 3, 4], dtype=np.int32),
                                    long_name='x', units='1'), 1)
        cube.add_dim_coord(DimCoord(np.array([0, 1, 2, 3], dtype=np.int32),
                                    long_name='y', units='1'), 0)

        for name, value, dim in zip(['a', 'b'], [a, b], [a_dim, b_dim]):
            dtype = np.str if isinstance(value, six.string_types) else np.float32
            ctype = DimCoord if dim else AuxCoord
            coord = ctype(np.array([value], dtype=dtype),
                          long_name=name, units='1')
            cube.add_aux_coord(coord)

        return cube

    def test_string_a_with_aux(self):
        templates = (('a', 0), ('b', 1), ('c', 2), ('d', 3))
        cubes = [self._make_cube(a, b) for a, b in templates]
        cube = iris.cube.CubeList(cubes).merge()[0]
        self.assertCML(cube, ('merge', 'string_a_with_aux.cml'),
                       checksum=False)
        self.assertIsInstance(cube.coord('a'), AuxCoord)
        self.assertIsInstance(cube.coord('b'), DimCoord)
        self.assertTrue(cube.coord('b') in cube.dim_coords)

    def test_string_b_with_aux(self):
        templates = ((0, 'a'), (1, 'b'), (2, 'c'), (3, 'd'))
        cubes = [self._make_cube(a, b) for a, b in templates]
        cube = iris.cube.CubeList(cubes).merge()[0]
        self.assertCML(cube, ('merge', 'string_b_with_aux.cml'),
                       checksum=False)
        self.assertIsInstance(cube.coord('a'), DimCoord)
        self.assertTrue(cube.coord('a') in cube.dim_coords)
        self.assertIsInstance(cube.coord('b'), AuxCoord)

    def test_string_a_with_dim(self):
        templates = (('a', 0), ('b', 1), ('c', 2), ('d', 3))
        cubes = [self._make_cube(a, b, b_dim=True) for a, b in templates]
        cube = iris.cube.CubeList(cubes).merge()[0]
        self.assertCML(cube, ('merge', 'string_a_with_dim.cml'),
                       checksum=False)
        self.assertIsInstance(cube.coord('a'), AuxCoord)
        self.assertIsInstance(cube.coord('b'), DimCoord)
        self.assertTrue(cube.coord('b') in cube.dim_coords)

    def test_string_b_with_aux(self):
        templates = ((0, 'a'), (1, 'b'), (2, 'c'), (3, 'd'))
        cubes = [self._make_cube(a, b, a_dim=True) for a, b in templates]
        cube = iris.cube.CubeList(cubes).merge()[0]
        self.assertCML(cube, ('merge', 'string_b_with_dim.cml'),
                       checksum=False)
        self.assertIsInstance(cube.coord('a'), DimCoord)
        self.assertTrue(cube.coord('a') in cube.dim_coords)
        self.assertIsInstance(cube.coord('b'), AuxCoord)

    def test_string_a_b(self):
        templates = (('a', '0'), ('b', '1'), ('c', '2'), ('d', '3'))
        cubes = [self._make_cube(a, b) for a, b in templates]
        cube = iris.cube.CubeList(cubes).merge()[0]
        self.assertCML(cube, ('merge', 'string_a_b.cml'),
                       checksum=False)
        self.assertIsInstance(cube.coord('a'), AuxCoord)
        self.assertIsInstance(cube.coord('b'), AuxCoord)

    def test_a_aux_b_aux(self):
        templates = ((0, 10), (1, 11), (2, 12), (3, 13))
        cubes = [self._make_cube(a, b) for a, b in templates]
        cube = iris.cube.CubeList(cubes).merge()[0]
        self.assertCML(cube, ('merge', 'a_aux_b_aux.cml'),
                       checksum=False)
        self.assertIsInstance(cube.coord('a'), DimCoord)
        self.assertTrue(cube.coord('a') in cube.dim_coords)
        self.assertIsInstance(cube.coord('b'), DimCoord)
        self.assertTrue(cube.coord('b') in cube.aux_coords)

    def test_a_aux_b_dim(self):
        templates = ((0, 10), (1, 11), (2, 12), (3, 13))
        cubes = [self._make_cube(a, b, b_dim=True) for a, b in templates]
        cube = iris.cube.CubeList(cubes).merge()[0]
        self.assertCML(cube, ('merge', 'a_aux_b_dim.cml'),
                       checksum=False)
        self.assertIsInstance(cube.coord('a'), DimCoord)
        self.assertTrue(cube.coord('a') in cube.aux_coords)
        self.assertIsInstance(cube.coord('b'), DimCoord)
        self.assertTrue(cube.coord('b') in cube.dim_coords)

    def test_a_dim_b_aux(self):
        templates = ((0, 10), (1, 11), (2, 12), (3, 13))
        cubes = [self._make_cube(a, b, a_dim=True) for a, b in templates]
        cube = iris.cube.CubeList(cubes).merge()[0]
        self.assertCML(cube, ('merge', 'a_dim_b_aux.cml'),
                       checksum=False)
        self.assertIsInstance(cube.coord('a'), DimCoord)
        self.assertTrue(cube.coord('a') in cube.dim_coords)
        self.assertIsInstance(cube.coord('b'), DimCoord)
        self.assertTrue(cube.coord('b') in cube.aux_coords)

    def test_a_dim_b_dim(self):
        templates = ((0, 10), (1, 11), (2, 12), (3, 13))
        cubes = [self._make_cube(a, b, a_dim=True, b_dim=True) \
                     for a, b in templates]
        cube = iris.cube.CubeList(cubes).merge()[0]
        self.assertCML(cube, ('merge', 'a_dim_b_dim.cml'),
                       checksum=False)
        self.assertIsInstance(cube.coord('a'), DimCoord)
        self.assertTrue(cube.coord('a') in cube.dim_coords)
        self.assertIsInstance(cube.coord('b'), DimCoord)
        self.assertTrue(cube.coord('b') in cube.aux_coords)


class TestTimeTripleMerging(tests.IrisTest):
    def _make_cube(self, a, b, c, data=0):
        cube_data = np.empty((4, 5), dtype=np.float32)
        cube_data[:] = data
        cube = iris.cube.Cube(cube_data)
        cube.add_dim_coord(DimCoord(np.array([0, 1, 2, 3, 4], dtype=np.int32), long_name='x', units='1'), 1)
        cube.add_dim_coord(DimCoord(np.array([0, 1, 2, 3], dtype=np.int32), long_name='y', units='1'), 0)
        cube.add_aux_coord(DimCoord(np.array([a], dtype=np.int32), standard_name='forecast_period', units='1'))
        cube.add_aux_coord(DimCoord(np.array([b], dtype=np.int32), standard_name='forecast_reference_time', units='1'))
        cube.add_aux_coord(DimCoord(np.array([c], dtype=np.int32), standard_name='time', units='1'))
        return cube

    def _test_triples(self, triples, filename):
        cubes = [self._make_cube(fp, rt, t) for fp, rt, t in triples]
        cube = iris.cube.CubeList(cubes).merge()
        self.assertCML(cube, ('merge', 'time_triple_' + filename + '.cml'), checksum=False)

    def test_single_forecast(self):
        # A single forecast series (i.e. from a single reference time)
        # => fp, t: 4; rt: scalar
        triples = (
            (0, 10, 10), (1, 10, 11), (2, 10, 12), (3, 10, 13),
        )
        self._test_triples(triples, 'single_forecast')

    def test_successive_forecasts(self):
        # Three forecast series from successively later reference times
        # => rt, t: 3; fp, t: 4
        triples = (
            (0, 10, 10), (1, 10, 11), (2, 10, 12), (3, 10, 13),
            (0, 11, 11), (1, 11, 12), (2, 11, 13), (3, 11, 14),
            (0, 12, 12), (1, 12, 13), (2, 12, 14), (3, 12, 15),
        )
        self._test_triples(triples, 'successive_forecasts')

    def test_time_vs_ref_time(self):
        # => fp, t: 4; fp, rt: 3
        triples = (
            (2, 10, 12), (3, 10, 13), (4, 10, 14), (5, 10, 15),
            (1, 11, 12), (2, 11, 13), (3, 11, 14), (4, 11, 15),
            (0, 12, 12), (1, 12, 13), (2, 12, 14), (3, 12, 15),
        )
        self._test_triples(triples, 'time_vs_ref_time')

    def test_time_vs_forecast(self):
        # => rt, t: 4, fp, rt: 3
        triples = (
            (0, 10, 10), (0, 11, 11), (0, 12, 12), (0, 13, 13),
            (1,  9, 10), (1, 10, 11), (1, 11, 12), (1, 12, 13),
            (2,  8, 10), (2,  9, 11), (2, 10, 12), (2, 11, 13),
        )
        self._test_triples(triples, 'time_vs_forecast')

    def test_time_non_dim_coord(self):
        # => rt: 1 fp, t (bounded): 2
        triples = (
            (5, 0, 2.5), (10, 0, 5),
        )
        cubes = [self._make_cube(fp, rt, t) for fp, rt, t in triples]
        for end_time, cube in zip([5, 10], cubes):
            cube.coord('time').bounds = [0, end_time]
        cube, = iris.cube.CubeList(cubes).merge()
        self.assertCML(cube, ('merge', 'time_triple_time_non_dim_coord.cml'), checksum=False)
        # make sure that forecast_period is the dimensioned coordinate (as time becomes an AuxCoord)
        self.assertEqual(cube.coord(dimensions=0, dim_coords=True).name(), 'forecast_period')

    def test_independent(self):
        # => fp: 2; rt: 2; t: 2
        triples = (
            (0, 10, 10), (0, 11, 10),
            (0, 10, 11), (0, 11, 11),
            (1, 10, 10), (1, 11, 10),
            (1, 10, 11), (1, 11, 11),
        )
        self._test_triples(triples, 'independent')

    def test_series(self):
        # => fp, rt, t: 5 (with only t being definitive).
        triples = (
            (0, 10, 10),
            (0, 11, 11),
            (0, 12, 12),
            (1, 12, 13),
            (2, 12, 14),
        )
        self._test_triples(triples, 'series')

    def test_non_expanding_dimension(self):
        triples = (
            (0, 10, 0), (0, 20, 1), (0, 20, 0),
        )
        # => fp: scalar; rt, t: 3 (with no time being definitive)
        self._test_triples(triples, 'non_expanding')

    def test_duplicate_data(self):
        # test what happens when we have repeated time coordinates (i.e. duplicate data)
        cube1 = self._make_cube(0, 10, 0)
        cube2 = self._make_cube(1, 20, 1)
        cube3 = self._make_cube(1, 20, 1)

        # check that we get a duplicate data error when unique is True
        with self.assertRaises(iris.exceptions.DuplicateDataError):
            iris.cube.CubeList([cube1, cube2, cube3]).merge()

        cubes = iris.cube.CubeList([cube1, cube2, cube3]).merge(unique=False)
        self.assertCML(cubes, ('merge', 'time_triple_duplicate_data.cml'), checksum=False)

    def test_simple1(self):
        cube1 = self._make_cube(0, 10, 0)
        cube2 = self._make_cube(1, 20, 1)
        cube3 = self._make_cube(2, 20, 0)
        cube = iris.cube.CubeList([cube1, cube2, cube3]).merge()
        self.assertCML(cube, ('merge', 'time_triple_merging1.cml'), checksum=False)

    def test_simple2(self):
        cubes = iris.cube.CubeList([
                                    self._make_cube(0, 0, 0),
                                    self._make_cube(1, 0, 1),
                                    self._make_cube(2, 0, 2),
                                    self._make_cube(0, 1, 3),
                                    self._make_cube(1, 1, 4),
                                    self._make_cube(2, 1, 5),
                                   ])
        cube = cubes.merge()[0]
        self.assertCML(cube, ('merge', 'time_triple_merging2.cml'), checksum=False)

        cube = iris.cube.CubeList(cubes[:-1]).merge()[0]
        self.assertCML(cube, ('merge', 'time_triple_merging3.cml'), checksum=False)

    def test_simple3(self):
        cubes = iris.cube.CubeList([
                                    self._make_cube(0, 0, 0),
                                    self._make_cube(0, 1, 1),
                                    self._make_cube(0, 2, 2),
                                    self._make_cube(1, 0, 3),
                                    self._make_cube(1, 1, 4),
                                    self._make_cube(1, 2, 5),
                                   ])
        cube = cubes.merge()[0]
        self.assertCML(cube, ('merge', 'time_triple_merging4.cml'), checksum=False)

        cube = iris.cube.CubeList(cubes[:-1]).merge()[0]
        self.assertCML(cube, ('merge', 'time_triple_merging5.cml'), checksum=False)


class TestCubeMergeTheoretical(tests.IrisTest):
    def test_simple_bounds_merge(self):
        cube1 = iris.tests.stock.simple_2d()
        cube2 = iris.tests.stock.simple_2d()

        cube1.add_aux_coord(DimCoord(np.int32(10), long_name='pressure', units='Pa'))
        cube2.add_aux_coord(DimCoord(np.int32(11), long_name='pressure', units='Pa'))

        r = iris.cube.CubeList([cube1, cube2]).merge()
        self.assertCML(r, ('cube_merge', 'test_simple_bound_merge.cml'))

    def test_simple_multidim_merge(self):
        cube1 = iris.tests.stock.simple_2d_w_multidim_coords()
        cube2 = iris.tests.stock.simple_2d_w_multidim_coords()

        cube1.add_aux_coord(DimCoord(np.int32(10), long_name='pressure', units='Pa'))
        cube2.add_aux_coord(DimCoord(np.int32(11), long_name='pressure', units='Pa'))

        r = iris.cube.CubeList([cube1, cube2]).merge()[0]
        self.assertCML(r, ('cube_merge', 'multidim_coord_merge.cml'))

        # try transposing the cubes first
        cube1.transpose([1, 0])
        cube2.transpose([1, 0])
        r = iris.cube.CubeList([cube1, cube2]).merge()[0]
        self.assertCML(r, ('cube_merge', 'multidim_coord_merge_transpose.cml'))

    def test_simple_points_merge(self):
        cube1 = iris.tests.stock.simple_2d(with_bounds=False)
        cube2 = iris.tests.stock.simple_2d(with_bounds=False)

        cube1.add_aux_coord(DimCoord(np.int32(10), long_name='pressure', units='Pa'))
        cube2.add_aux_coord(DimCoord(np.int32(11), long_name='pressure', units='Pa'))

        r = iris.cube.CubeList([cube1, cube2]).merge()
        self.assertCML(r, ('cube_merge', 'test_simple_merge.cml'))

        # check that the unique merging raises a Duplicate data error
        self.assertRaises(iris.exceptions.DuplicateDataError, iris.cube.CubeList([cube1, cube1]).merge, unique=True)

        # check that non unique merging returns both cubes
        r = iris.cube.CubeList([cube1, cube1]).merge(unique=False)
        self.assertCML(r[0], ('cube_merge', 'test_orig_point_cube.cml'))
        self.assertCML(r[1], ('cube_merge', 'test_orig_point_cube.cml'))

        # test attribute merging
        cube1.attributes['my_attr1'] = 'foo'
        r = iris.cube.CubeList([cube1, cube2]).merge()
        # result should be 2 cubes
        self.assertCML(r, ('cube_merge', 'test_simple_attributes1.cml'))

        cube2.attributes['my_attr1'] = 'bar'
        r = iris.cube.CubeList([cube1, cube2]).merge()
        # result should be 2 cubes
        self.assertCML(r, ('cube_merge', 'test_simple_attributes2.cml'))

        cube2.attributes['my_attr1'] = 'foo'
        r = iris.cube.CubeList([cube1, cube2]).merge()
        # result should be 1 cube
        self.assertCML(r, ('cube_merge', 'test_simple_attributes3.cml'))


if __name__ == "__main__":
    tests.main()
