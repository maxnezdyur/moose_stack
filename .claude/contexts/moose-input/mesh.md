# Authoring inputs: Mesh (`[Mesh]` block)

Reach for this guide when you need to author or edit the `[Mesh]` block of a `.i` file by **picking from the catalog** of registered MOOSE mesh generators (file readers, scratch generators, transformers, surgery operators) plus the top-level `[Mesh]` meta-options. If you already have an Exodus/Nemesis/Abaqus file on disk, jump to the read-from-file catalog below. If you need to build geometry from scratch and chain operations (subdomains, sidesets, refinement) before solve time, you almost always want named generator sub-blocks chained via `input = ...`. If the geometry truly does not exist as any combination of catalog generators, you may have to write a new C++ `MeshGenerator` — that's outside the scope of this guide.

Citations are repo-relative from `/Users/maxnezdyur/projects/moose_stack/moose`. Each catalog entry cites both the **source header** (`<file>:<line of class>`) and one **canonical example .i** (`<file>:<line of the sub-block>`). Generators that live in modules cite under `modules/<module>/...`.

## When to use this (vs alternatives)

Decide on **how the geometry enters MOOSE** first, then **what to do to it** before solve.

1. Geometry already lives on disk (Exodus `.e`, Nemesis `.nemesis.*`, Abaqus `.inp`, Tetgen, Gmsh `.msh`, XDA/XDR): use **`FileMeshGenerator`** as the first sub-block, or the legacy `[Mesh] file = ...` shorthand for read-only inputs. Subsequent surgery (sidesets, blocks) chains off it via `input = file_in`.
2. Geometry is a simple Cartesian box, line, or grid: **`GeneratedMeshGenerator`** (most common 1D/2D/3D scratch mesh). Use `CartesianMeshGenerator` when you need non-uniform spacing per axis.
3. Geometry has rotational symmetry (annulus, polygon, reactor pin): pick from the polar/concentric family — `AnnularMeshGenerator`, `SpiralAnnularMeshGenerator`, `ConcentricCircleMeshGenerator`, `PolygonConcentricCircleMeshGenerator` (reactor module), `SphereMeshGenerator`.
4. Geometry comes from raster/voxel data (CT scan, image stack): **`ImageMeshGenerator`**.
5. Mesh must be **distributed-by-construction** (too big for `replicated`): **`DistributedRectilinearMeshGenerator`**, plus `parallel_type = distributed` at the top-level `[Mesh]`.
6. You need to **combine, copy, stack, or transform** existing pieces: `CombinerGenerator`, `StackGenerator`, `MeshCollectionGenerator`, `TransformGenerator`, `MeshExtruderGenerator`, `AdvancedExtruderGenerator`, `TiledMeshGenerator`.
7. You need to **rename / split / delete / annotate** subdomains and sidesets after the geometry exists: pick from the surgery family — `SubdomainBoundingBoxGenerator`, `SubdomainPerElementGenerator`, `RenameBlockGenerator`, `RenameBoundaryGenerator`, `SideSetsFromNormalsGenerator`, `SideSetsFromPointsGenerator`, `SideSetsBetweenSubdomainsGenerator`, `BreakBoundaryOnSubdomainGenerator`, `BlockDeletionGenerator`, `LowerDBlockFromSidesetGenerator` (mortar prep), `BreakMeshByBlockGenerator` (cohesive/mortar prep), `NodeSetsFromSideSetsGenerator`.
8. You need solver-time refinement of specific regions baked into the initial mesh: `RefineBlockGenerator`, `RefineSidesetGenerator`, or the top-level shorthand `[Mesh] uniform_refine = N`.

The legacy `[Mesh] type = FileMesh` / `type = GeneratedMesh` shortcut still works but is **discouraged** for new inputs — it bypasses the generator pipeline, so you cannot chain surgery onto it. Use `FileMeshGenerator` / `GeneratedMeshGenerator` instead. The one supported `[Mesh] file = path.e` shorthand (no `type =` line, just `file =`) is still common in legacy regression tests.

## Catalog

### Read from file

##### `FileMesh` (legacy `[Mesh] type = FileMesh`)
- Source: `framework/include/mesh/FileMesh.h:14`
- Example: `test/tests/mesh/abaqus_input/testcube_elem_id.i:1` (uses `[Mesh] file = ... type = FileMesh`)
- Legacy `MooseMesh` subclass selected by `[Mesh] type = FileMesh`. No generator pipeline — cannot be chained.
- Required: `file`.
- Useful: `parallel_type`, `partitioner`, `coord_type`, `displacements` (these are top-level `[Mesh]` params, not generator params here).

##### `[Mesh] file = ...` shorthand
- Source: `framework/src/mesh/FileMesh.C:25` (registers `FileMesh`; the shorthand selects this when `file` is set without a `type`)
- Example: `test/tests/mesh/named_entities/named_entities_test.i:1` (just `[Mesh] / file = named_entities.e`)
- Read-only convenience for legacy inputs. No `[./gen]` sub-block, no generator chain. Add nothing else inside `[Mesh]` — meta-options like `uniform_refine` and `displacements` still apply at top level.
- Required: `file`.
- Useful: same top-level `[Mesh]` meta-options as `FileMesh`.

##### `FileMeshGenerator`
- Source: `framework/include/meshgenerators/FileMeshGenerator.h:17`
- Example: `test/tests/meshgenerators/file_mesh_generator/file_mesh_generator.i:1` (sub-block at line 3)
- Modern way to read a mesh file. Output of this generator is the named sub-block (e.g. `fmg`), which downstream generators reference via `input = fmg`. Supports Exodus, Nemesis, Gmsh, XDA, Abaqus, Tetgen, IsogeometricAnalysis IGS files.
- Required: `file`.
- Useful: `use_for_exodus_restart`, `exodus_extra_element_integers`, `discontinuous_spline_extraction`, `clear_spline_nodes`.

### Generate from scratch

##### `GeneratedMeshGenerator`
- Source: `framework/include/meshgenerators/GeneratedMeshGenerator.h:18`
- Example: `test/tests/meshgenerators/generated_mesh_generator/generated_mesh_generator.i:1` (sub-block at line 3)
- Cartesian box of structured elements in 1D/2D/3D. Auto-creates sidesets `left`/`right`/`top`/`bottom`/`front`/`back` (1D: only `left`/`right`).
- Required: `dim` (1, 2, or 3), and per-axis counts: `nx`, plus `ny` if `dim>=2`, `nz` if `dim==3`.
- Useful: `xmin`/`xmax`/`ymin`/`ymax`/`zmin`/`zmax` (defaults `[0,1]`), `elem_type` (`EDGE2|EDGE3|QUAD4|QUAD9|HEX8|HEX27|TRI3|TET4|...`), `bias_x`/`bias_y`/`bias_z`, `subdomain_ids` (for striped subdomains), `extra_element_integers`, `boundary_name_prefix`.

##### `CartesianMeshGenerator`
- Source: `framework/include/meshgenerators/CartesianMeshGenerator.h:18`
- Example: `test/tests/meshgenerators/cartesian_mesh_generator/cartesian_mesh_2D.i:1` (sub-block at line 3)
- Like `GeneratedMeshGenerator` but with **non-uniform** per-axis spacing and per-cell subdomain IDs. Use when you need stretched grids or pre-split subdomains in a single shot.
- Required: `dim`, `dx` (vector of per-cell sizes along x), plus `dy`/`dz` for higher dim, and `ix`/`iy`/`iz` (subdivisions per `dx` entry).
- Useful: `subdomain_id` (vector covering the full block grid).

##### `AnnularMeshGenerator`
- Source: `framework/include/meshgenerators/AnnularMeshGenerator.h:18`
- Example: `test/tests/meshgenerators/annular_mesh_generator/annular_mesh_generator.i:1` (sub-block at line 3)
- 2D annular wedge or full disk between `rmin` and `rmax`, between `tmin` and `tmax` radians. Sidesets named `rmin`/`rmax`/`tmin`/`tmax`.
- Required: `nr`, `nt`, `rmin`, `rmax`.
- Useful: `tmin`/`tmax` (defaults `0` / `2*pi`), `dmin`/`dmax` (degrees alternative), `growth_r` (radial bias), `quad_subdomain_id`/`tri_subdomain_id`, `boundary_name_prefix`.

##### `SpiralAnnularMeshGenerator`
- Source: `framework/include/meshgenerators/SpiralAnnularMeshGenerator.h:17`
- Example: `test/tests/meshgenerators/spiral_annular_mesh_generator/spiral_annular_mesh_generator.i:1` (sub-block at line 3)
- 2D triangular annular mesh built spirally outward; useful when an `AnnularMeshGenerator` quad mesh would have bad aspect ratios near the inner radius.
- Required: `inner_radius`, `outer_radius`, `nodes_per_ring`, `num_rings`.
- Useful: `radial_bias`, `cylinder_bc_only` (whether to put a sideset on the outer ring only).

##### `RinglebMeshGenerator`
- Source: `framework/include/meshgenerators/RinglebMeshGenerator.h:17`
- Example: `test/tests/meshgenerators/ringleb_mesh_generator/ringleb_mesh_generator.i:1` (sub-block at line 3)
- Ringleb-flow analytical-streamline mesh for compressible-CFD verification.
- Required: `kmin`, `kmax`, `gamma`, `num_k_pts`, `num_q_pts`, `n_extra_q_pts`.
- Useful: `triangles` (split each quad into two triangles).

##### `ConcentricCircleMeshGenerator`
- Source: `framework/include/meshgenerators/ConcentricCircleMeshGenerator.h:18`
- Example: `test/tests/meshgenerators/concentric_circle_mesh_generator/concentric_circle_mesh_generator.i:1` (sub-block at line 3)
- 2D mesh of nested concentric rings (pin-cell style), each ring its own subdomain. Outer boundary can be circular or square.
- Required: `num_sectors`, `radii`, `rings`, `has_outer_square`, `pitch` (only when `has_outer_square = true`).
- Useful: `preserve_volumes` (radial scaling), `portion` (`full|top_half|right_half|...`).

##### `PolygonConcentricCircleMeshGenerator`
- Source: `modules/reactor/include/meshgenerators/PolygonConcentricCircleMeshGenerator.h:18`
- Example: `modules/reactor/test/tests/meshgenerators/polygon_concentric_circle_mesh_generator/poly_2d.i:1` (sub-block at line 3)
- Reactor-module pin-cell generator: concentric rings inside a regular `n`-sided polygon (hex, square, triangle). The standard hex pin generator.
- Required: `num_sides`, `num_sectors_per_side`, `polygon_size`, `ring_radii`, `ring_intervals`, `background_intervals`.
- Useful: `polygon_size_style` (`apothem|radius`), `ring_block_ids`/`background_block_ids`/`ducts_block_ids`, `external_boundary_id`/`external_boundary_name`, `flat_side_up`, `quad_center_elements`.

##### `SphereMeshGenerator`
- Source: `framework/include/meshgenerators/SphereMeshGenerator.h:17`
- Example: `test/tests/meshgenerators/sphere_mesh_generator/sphere.i` (search for `type = SphereMeshGenerator`)
- 3D sphere mesh.
- Required: `radius`, `nr`.
- Useful: `n_smooth` (Laplacian smoothing iterations).

##### `DistributedRectilinearMeshGenerator`
- Source: `framework/include/meshgenerators/DistributedRectilinearMeshGenerator.h:26`
- Example: `test/tests/meshgenerators/distributed_rectilinear/generator/distributed_rectilinear_mesh_generator.i:1` (sub-block at line 3)
- Cartesian rectilinear mesh that is built **distributed by construction** — no rank ever sees the full mesh. Use for large 3D problems where `replicated` would OOM the host. Pair with top-level `[Mesh] parallel_type = distributed`.
- Required: `dim`, `nx` (and `ny`, `nz` per `dim`).
- Useful: `xmin`/`xmax`/`ymin`/`ymax`/`zmin`/`zmax`, `elem_type`, `bias_x`/`bias_y`/`bias_z`, `partition` (`linear|grid|...`), `num_cores_for_partition`.

##### `ImageMeshGenerator`
- Source: `framework/include/meshgenerators/ImageMeshGenerator.h:19`
- Example: `test/tests/meshgenerators/image_mesh_generator/image_mesh_generator.i:1` (sub-block at line 3)
- Builds a `GeneratedMeshGenerator`-style grid sized to a 2D image or 3D image stack. Pair with `ImageFunction`/`ImageSubdomainGenerator` to map pixel data onto the mesh.
- Required: `file` *or* `file_base` + `file_range` for stacks.
- Useful: `cells_per_pixel` (default 1), `scale`, `dim`.

### Combine / transform meshes

##### `CombinerGenerator`
- Source: `framework/include/meshgenerators/CombinerGenerator.h:19`
- Example: `test/tests/meshgenerators/combiner_generator/combiner_generator.i:1` (`CombinerGenerator` sub-block at line 9)
- Translates copies of one or more input meshes by a list of positions and unions them. Subdomain/sideset IDs from the inputs are *not* renumbered — collisions become merges. Use for arrays of identical pieces.
- Required: `inputs` (list of upstream generators), and either `positions` (vector of `(x y z)`) or `positions_file`.
- Useful: `avoid_merging_subdomains`, `avoid_merging_boundaries`, `merge_boundaries_with_same_name` (default true).

##### `StackGenerator`
- Source: `framework/include/meshgenerators/StackGenerator.h:19`
- Example: `test/tests/meshgenerators/stack_generator/stack_generator.i:1` (`StackGenerator` sub-block at line 44)
- Stacks `n` meshes along one axis with optional gaps. Each input must match in cross-section. Sidesets at the join become interior unless renamed.
- Required: `inputs`, `dim`.
- Useful: `bottom_boundary`, `top_boundary`, `axis` (`x|y|z`), `prevent_boundary_id_overlap`.

##### `MeshCollectionGenerator`
- Source: `framework/include/meshgenerators/MeshCollectionGenerator.h:19`
- Example: `test/tests/meshgenerators/mesh_collection_generator/mesh_collection_generator.i:1` (sub-block at line 24)
- Unions multiple input meshes **without translating them** (each input lives wherever it was generated). Subdomain/sideset IDs are preserved as-is.
- Required: `inputs`.

##### `TransformGenerator`
- Source: `framework/include/meshgenerators/TransformGenerator.h:19`
- Example: `test/tests/meshgenerators/transform_generator/translate.i:1` (sub-block at line 10)
- Applies a single rigid transform — translate / rotate / scale / shear — to one input mesh.
- Required: `input`, `transform` (`TRANSLATE|TRANSLATE_MIN_ORIGIN|TRANSLATE_CENTER_ORIGIN|ROTATE|SCALE`), `vector_value` (3-entry vector matching the transform).

##### `MeshExtruderGenerator`
- Source: `framework/include/meshgenerators/MeshExtruderGenerator.h:19`
- Example: `test/tests/meshgenerators/mesh_extruder_generator/gen_extrude.i:1` (sub-block at line 14)
- Extrudes a 1D mesh into 2D or a 2D mesh into 3D along a fixed direction. Single-layer extrusion in one direction. Older API; prefer `AdvancedExtruderGenerator` for new inputs.
- Required: `input`, `extrusion_vector`, `num_layers`.
- Useful: `bottom_sideset`, `top_sideset`, `existing_subdomains`/`layers`/`new_ids` (per-layer subdomain remap).

##### `AdvancedExtruderGenerator`
- Source: `framework/include/meshgenerators/AdvancedExtruderGenerator.h:19`
- Example: `test/tests/meshgenerators/advanced_extruder_generator/gen_extrude.i:1` (sub-block at line 14)
- Multi-segment extrusion with per-segment heights, layer counts, layer-by-layer subdomain swaps, and per-segment boundary swaps.
- Required: `input`, `direction` (`(x y z)`), `heights`, `num_layers`.
- Useful: `bottom_boundary`, `top_boundary`, `subdomain_swaps`, `boundary_swaps`, `bottom_sideset`, `top_sideset`, `extra_element_integer_swaps`.

##### `TiledMeshGenerator`
- Source: `framework/include/meshgenerators/TiledMeshGenerator.h:17`
- Example: `test/tests/meshgenerators/tiled_mesh_generator/tiled_mesh_generator.i:1` (sub-block at line 8)
- Replicates one input mesh in a 3D `(x_tiles, y_tiles, z_tiles)` grid by stitching matching boundaries. Cheaper than `CombinerGenerator` when faces actually align.
- Required: `input`, plus boundary-pair params (`left_boundary`/`right_boundary`/`top_boundary`/`bottom_boundary`/`front_boundary`/`back_boundary`).
- Useful: `x_width`, `y_width`, `z_width`, `x_tiles`, `y_tiles`, `z_tiles`.

### Subdomain / sideset surgery

##### `SubdomainBoundingBoxGenerator`
- Source: `framework/include/meshgenerators/SubdomainBoundingBoxGenerator.h:25`
- Example: `test/tests/meshgenerators/subdomain_bounding_box_generator/subdomain_bounding_box_generator_inside.i:1` (sub-block at line 13)
- Reassigns subdomain IDs of elements that fall inside (or outside) an axis-aligned bounding box.
- Required: `input`, `block_id`, `bottom_left`, `top_right`.
- Useful: `block_name`, `location` (`INSIDE|OUTSIDE`, default `INSIDE`), `restricted_subdomains`, `integer_name` (assign extra element integer instead of subdomain).

##### `SubdomainPerElementGenerator`
- Source: `framework/include/meshgenerators/SubdomainPerElementGenerator.h:17`
- Example: `test/tests/meshgenerators/element_subdomain_id_generator/quad_with_subdomainid_test.i:1` (sub-block at line 14)
- Sets subdomain ID per element from a flat ID list (or only on a list of element IDs). Used when subdomain assignment doesn't fit a bounding box.
- Required: `input`, `subdomain_ids`.
- Useful: `element_ids` (target only listed elements; otherwise `subdomain_ids` must cover all elements).

##### `RenameBlockGenerator`
- Source: `framework/include/meshgenerators/RenameBlockGenerator.h:17`
- Example: `test/tests/meshgenerators/rename_block_generator/rename_block.i:1` (sub-block at line 13)
- Renames or merges subdomains. Primary tool for giving named subdomains downstream-friendly handles like `fuel`/`clad`/`coolant`.
- Required: `input`, plus exactly one of (`old_block`/`new_block`) pairs by name or by id.
- Useful: chain multiple `RenameBlockGenerator` sub-blocks for multi-step renames.

##### `RenameBoundaryGenerator`
- Source: `framework/include/meshgenerators/RenameBoundaryGenerator.h:17`
- Example: `test/tests/meshgenerators/rename_boundary_generator/rename_boundary.i:1` (sub-block at line 11)
- Same as `RenameBlockGenerator` but for sidesets/nodesets.
- Required: `input`, `old_boundary`/`new_boundary` (by id or name).

##### `SideSetsFromNormalsGenerator`
- Source: `framework/include/meshgenerators/SideSetsFromNormalsGenerator.h:17`
- Example: `test/tests/meshgenerators/sidesets_from_normals_generator/sidesets_cylinder_normals.i:1` (sub-block at line 9)
- Builds sidesets by walking the boundary and grouping faces whose outward normals match supplied vectors within a tolerance. Use on imported CAD/Exodus meshes that lack named sidesets.
- Required: `input`, `new_boundary`, `normals` (one normal per output sideset).
- Useful: `variance` (angular tolerance, radians), `fixed_normal`, `replace`.

##### `SideSetsFromPointsGenerator`
- Source: `framework/include/meshgenerators/SideSetsFromPointsGenerator.h:18`
- Example: `test/tests/meshgenerators/sidesets_from_points_generator/sidesets_from_points.i:1` (sub-block at line 9)
- Like `SideSetsFromNormalsGenerator`, but the seed face containing each supplied point is found, and the sideset is grown from there along contiguous coplanar faces.
- Required: `input`, `new_boundary`, `points`.

##### `SideSetsBetweenSubdomainsGenerator`
- Source: `framework/include/meshgenerators/SideSetsBetweenSubdomainsGenerator.h:18`
- Example: `test/tests/meshgenerators/sidesets_between_subdomains_generator/sideset_between_subdomains.i:1` (sub-block at line 22)
- Creates a new sideset on every face that sits between two named subdomains. Foundational input for `[InterfaceKernels]` and mortar contact.
- Required: `input`, `primary_block`, `paired_block`, `new_boundary`.

##### `BreakBoundaryOnSubdomainGenerator`
- Source: `framework/include/meshgenerators/BreakBoundaryOnSubdomainGenerator.h:17`
- Example: `test/tests/meshgenerators/break_boundary_on_subdomain/break_boundary_on_subdomain.i:1` (sub-block at line 39)
- Splits a sideset into per-subdomain pieces (e.g. `left` becomes `left_1` and `left_2` once two subdomains touch it). Needed when a Dirichlet BC must be applied to only one subdomain side of a shared boundary.
- Required: `input`.
- Useful: `boundaries` (default: all), `block` (default: all subdomains touching the boundary).

##### `BlockDeletionGenerator`
- Source: `framework/include/meshgenerators/BlockDeletionGenerator.h:17`
- Example: `test/tests/meshgenerators/block_deletion_generator/block_deletion_test1.i:1` (sub-block at line 22)
- Removes all elements belonging to listed subdomains. Optionally preserves the resulting external surfaces with a new boundary name.
- Required: `input`, `block` (or `block_id`).
- Useful: `new_boundary` (name to apply to the freshly-exposed surface), `delete_exteriors` (default true), `keep_blocks` (negate).

##### `LowerDBlockFromSidesetGenerator` (mortar prep)
- Source: `framework/include/meshgenerators/LowerDBlockFromSidesetGenerator.h:17`
- Example: `test/tests/meshgenerators/lower_d_block_generator/names.i:1` (sub-block at line 10)
- Adds a *lower-dimensional* element block (1D faces in 2D, 2D faces in 3D) co-located with a sideset. Required to live a Lagrange-multiplier variable on a mortar interface.
- Required: `input`, `sidesets`, `new_block_id` *or* `new_block_name`.

##### `BreakMeshByBlockGenerator` (cohesive / mortar prep)
- Source: `framework/include/meshgenerators/BreakMeshByBlockGenerator.h:18`
- Example: `test/tests/meshgenerators/break_mesh_by_block_generator/break_mesh_2DJunction_auto.i:1` (sub-block at line 8)
- Duplicates nodes along inter-block faces, producing a discontinuous mesh suitable for cohesive-zone modeling or mortar coupling between subdomains.
- Required: `input`.
- Useful: `surface_rename` (named per-pair sidesets), `block_pairs` (restrict to specific block adjacencies), `add_interface_on_two_sides`, `split_interface`.

##### `NodeSetsFromSideSetsGenerator`
- Source: `framework/include/meshgenerators/NodeSetsFromSideSetsGenerator.h:17`
- Example: `test/tests/meshgenerators/nodesets_from_sidesets_generator/from_sides.i:1` (sub-block at line 28)
- Promotes existing sidesets to nodesets (e.g. needed by some nodal BCs that only consume nodesets).
- Required: `input`.
- Useful: `nodesets_to_add` (subset of sidesets; default: all).

### Refinement at mesh-gen time

##### `RefineBlockGenerator`
- Source: `framework/include/meshgenerators/RefineBlockGenerator.h:17`
- Example: `test/tests/meshgenerators/refine_block_generator/test_single.i:1` (sub-block at line 20)
- Applies `n` levels of uniform refinement only to listed subdomains. Cheaper than refining the whole mesh, generates non-conforming hanging nodes which MOOSE handles natively.
- Required: `input`, `block`, `refinement` (vector of refinement levels, one per block).
- Useful: `enable_neighbor_refinement` (default true; one extra layer outside the block to keep transitions sane).

##### `RefineSidesetGenerator`
- Source: `framework/include/meshgenerators/RefineSidesetGenerator.h:17`
- Example: `test/tests/meshgenerators/refine_sideset_generator/test_left.i:1` (sub-block at line 19)
- Refines elements that touch one or more sidesets `n` levels. Use to resolve boundary layers without refining the interior.
- Required: `input`, `boundaries`, `refinement` (per-sideset levels), `boundary_side` (`primary|secondary|both`).
- Useful: `enable_neighbor_refinement` (default true).

##### `[Mesh] uniform_refine = N` (top-level shorthand)
- Source: top-level `[Mesh]` parameter; not a generator. See top-level cross-cutting concerns below.
- Example: `test/tests/mesh/uniform_refine/3d_diffusion.i:9` (`uniform_refine = 1` line)
- Refines the *entire* mesh `N` times after all generators have run, before solve. Equivalent to `Adaptivity/Markers/...` with the `uniform` marker but cheaper because it's done once. Prefer this over the deprecated `UniformRefinement` mesh modifier.

### Mesh meta-options (top-level `[Mesh]` params)

These are **not** generator-specific. They live directly under `[Mesh]`, outside any sub-block, and apply globally after all generators have run.

- `displacements` — vector of variable names whose values are added to nodal coordinates each step. Required for any solid-mechanics input that uses `use_displaced_mesh = true` on its kernels/BCs/materials. Names must match `[Variables]` entries.
- `parallel_type` — `replicated` (default; every rank holds full mesh) or `distributed` (mesh partitioned across ranks). Use `distributed` for large 3D problems and always with `DistributedRectilinearMeshGenerator`. Some legacy postprocessors and many element-loop user objects need extra care under `distributed`.
- `partitioner` — partitioning algorithm: `linear` (default), `centroid`, `grid`, `hilbert_sfc`, `morton_sfc`, `parmetis`, `petsc`. Use `grid` (a libMesh-only Cartesian grid partitioner) for `DistributedRectilinearMeshGenerator`-style structured grids.
- `coord_type` — `XYZ` (default), `RZ`, or `RSPHERICAL`. Selects the integration weighting for the entire (or per-block, see `coord_block`) domain.
- `coord_block` — list of subdomains paired with `coord_type` to support **mixed-coordinate** problems (`XYZ` in one block, `RZ` in another).
- `uniform_refine` — integer `N`; uniformly refines the mesh `N` times after all generators run.
- `second_order` — `true` to promote a linear mesh to second-order (`QUAD4 -> QUAD9`, `HEX8 -> HEX27`, etc.). Required when using `SECOND` order Lagrange variables on a first-order generator.
- `allow_renumbering` — `false` to forbid libMesh element/node renumbering (preserve IDs when reading from an Exodus file with named integers).
- `nemesis` — `true` to read a pre-split Nemesis distributed file (`*.nemesis.<n>.<rank>`).
- `skip_partitioning` — `true` if the mesh already comes pre-partitioned (e.g. Nemesis) and you do not want libMesh to re-partition.

## Cross-cutting concerns

### Generator chaining and `input = ...`
- Every modern `[Mesh]` block is a chain of named sub-blocks: each sub-block's `[name]` becomes the generator's output handle. Downstream sub-blocks reference upstream output via `input = <name>` (or `inputs = '<a> <b>'` for combiners/stacks).
- The pipeline is a DAG: many generators can take the same input, and outputs unused by any sub-block are dropped unless one of them is the final mesh.
- The **final mesh** is the leaf — the generator whose output is not consumed by any other generator. If multiple leaves exist (ambiguous DAG), MOOSE errors and asks for `final_generator`.

### Final generator selection (`Mesh/final_generator`)
- Set `final_generator = <name>` directly under `[Mesh]` when the DAG has multiple leaves, or when you want to short-circuit a downstream branch (e.g. for debugging) without deleting it.
- See `test/tests/meshgenerators/final_generator/final_linear.i:2` for the canonical example.

### Naming conventions
- Subdomain (block) names and sideset (boundary) names are first-class strings — pass them around as names, not numeric IDs, throughout `[BCs]` / `[Materials]` / `[Kernels]`.
- Generators like `GeneratedMeshGenerator` create canonical sidesets `left`/`right`/`top`/`bottom`/`front`/`back`. Annular generators create `rmin`/`rmax`/`tmin`/`tmax`. Use `boundary_name_prefix` if you'll have multiple generated meshes in one input to avoid collisions.

### Displaced mesh
- `[Mesh] / displacements = 'disp_x disp_y disp_z'` is the *only* place displacements are configured for the mesh. Per-kernel `use_displaced_mesh = true` then applies them.
- A second, displaced copy of the mesh is built automatically — no second `[Mesh]` block is needed.

### Distributed-mesh limitations
- `parallel_type = distributed` disables some serial-only postprocessors and user objects. Most modern MOOSE objects support distributed; older test inputs sometimes assert `replicated` via `parallel_type = replicated` inside a `FileMeshGenerator` sub-block (a legacy override).
- `DistributedRectilinearMeshGenerator` always wants `parallel_type = distributed` at the top level.
- `Nemesis` distributed-file reads need both `nemesis = true` and `parallel_type = distributed`.

### Coordinate systems (`XYZ` / `RZ` / `RSPHERICAL`)
- `coord_type = RZ` interprets `x` as radius `r` and `y` as axial `z`. All volume integrals pick up the `2*pi*r` Jacobian automatically. Use for axisymmetric problems.
- `coord_type = RSPHERICAL` interprets `x` as the radial coordinate `r` only — meshes must be 1D. All integrals pick up the `4*pi*r^2` Jacobian.
- For mixed problems (XYZ in one subdomain, RZ in another), use `coord_block = '<block_xyz> <block_rz>'` with a matching `coord_type = 'XYZ RZ'` list.

### Refinement: when to use which knob
- `[Mesh] uniform_refine = N` — easiest; refines everything `N` times. Use for convergence studies.
- `RefineBlockGenerator` / `RefineSidesetGenerator` — bake region-specific refinement into the initial mesh, generating non-conforming hanging nodes. Cheaper than uniform refinement when only part of the domain needs resolution.
- `[Adaptivity]` block — solve-time adaptive refinement using error indicators / markers. Orthogonal to `[Mesh]` refinement; the two compose.

## Minimal scaffold

Read-from-file with sideset surgery:

```hit
[Mesh]
  [fmg]
    type = FileMeshGenerator
    file = my_geometry.e
  []
  [add_iface]
    type = SideSetsBetweenSubdomainsGenerator
    input = fmg
    primary_block = 'fuel'
    paired_block = 'clad'
    new_boundary = 'fuel_clad_iface'
  []
  [rename_outer]
    type = RenameBoundaryGenerator
    input = add_iface
    old_boundary = '101 102'
    new_boundary = 'cool_inlet cool_outlet'
  []
  coord_type = RZ
  uniform_refine = 1
[]
```

Chained scratch generation with named subdomains, sidesets, and per-block refinement:

```hit
[Mesh]
  [box]
    type = GeneratedMeshGenerator
    dim = 2
    nx = 20
    ny = 20
    xmin = 0
    xmax = 1
    ymin = 0
    ymax = 1
  []
  [left_half]
    type = SubdomainBoundingBoxGenerator
    input = box
    block_id = 1
    block_name = 'fuel'
    bottom_left = '0 0 0'
    top_right = '0.5 1 0'
  []
  [right_half]
    type = SubdomainBoundingBoxGenerator
    input = left_half
    block_id = 2
    block_name = 'clad'
    bottom_left = '0.5 0 0'
    top_right = '1 1 0'
  []
  [iface]
    type = SideSetsBetweenSubdomainsGenerator
    input = right_half
    primary_block = 'fuel'
    paired_block = 'clad'
    new_boundary = 'fuel_clad'
  []
  [refine_fuel]
    type = RefineBlockGenerator
    input = iface
    block = 'fuel'
    refinement = '1'
  []
  displacements = 'disp_x disp_y'
  parallel_type = replicated
[]
```
