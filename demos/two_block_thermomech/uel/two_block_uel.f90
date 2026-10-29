! Coupled temperature-displacement HEX8 user element (Abaqus UEL interface) for the
! two-block demo. Stand-in for the group's own UEL; the argument list is the Abaqus one.
!
! Nodal DOFs, node by node: ux, uy, uz, T (NDOFEL = 32).
! Integration: 2 x 2 x 2 Gauss points.
!
! Mechanics: small-strain Maxwell visco-elastic solid with thermal expansion, the model of
! the stand-in UMAT (umat/two_block_umat.f). The state variable Z is the accumulated
! equivalent viscous strain; it hardens the viscosity, eta = eta0 * (1 + cz * Z).
! Heat: rho c dT/dt = div(k grad T) + q, with q = phi^2 when PROPS(9) = 1 (block A).
! phi is PREDEF field 1 (value at the start of the increment, and its increment).
!
! PROPS(1) E      Young's modulus [Pa]
! PROPS(2) NU     Poisson's ratio [-]
! PROPS(3) ALPHA  coefficient of thermal expansion [1/K]
! PROPS(4) ETA0   shear viscosity at Z = 0 [Pa s]
! PROPS(5) CZ     hardening of the viscosity with Z [-]
! PROPS(6) K      thermal conductivity [W/(m K)]
! PROPS(7) RHO    density [kg/m^3]
! PROPS(8) CP     specific heat [J/(kg K)]
! PROPS(9) QFLAG  1: heat source phi^2 in this element, 0: none
!
! SVARS, per Gauss point g (7 values): stress xx yy zz xy xz yz, then Z. NSVARS = 56.
!
! RHS is the Abaqus residual (external minus internal), AMATRX = -dRHS/dU.
subroutine uel(rhs, amatrx, svars, energy, ndofel, nrhs, nsvars, props, nprops, coords, &
               mcrd, nnode, u, du, v, a, jtype, time, dtime, kstep, kinc, jelem, params, &
               ndload, jdltyp, adlmag, predef, npredf, lflags, mlvarx, ddlmag, mdload, &
               pnewdt, jprops, njprop, period)
  implicit none
  integer :: ndofel, nrhs, nsvars, nprops, mcrd, nnode, jtype, kstep, kinc, jelem
  integer :: ndload, npredf, mlvarx, mdload, njprop
  integer :: jdltyp(mdload, *), lflags(*), jprops(*)
  double precision :: rhs(mlvarx, *), amatrx(ndofel, ndofel), svars(nsvars), energy(8)
  double precision :: props(nprops), coords(mcrd, nnode), u(ndofel), du(mlvarx, *)
  double precision :: v(ndofel), a(ndofel), time(2), dtime, params(*)
  double precision :: adlmag(mdload, *), predef(2, npredf, nnode), ddlmag(mdload, *)
  double precision :: pnewdt, period

  integer, parameter :: nsv = 7
  ! the 8 corner nodes of the reference cube, in libMesh / Abaqus C3D8 order
  double precision, parameter :: xin(3, 8) = reshape([ &
      -1d0, -1d0, -1d0,   1d0, -1d0, -1d0,   1d0,  1d0, -1d0,  -1d0,  1d0, -1d0, &
      -1d0, -1d0,  1d0,   1d0, -1d0,  1d0,   1d0,  1d0,  1d0,  -1d0,  1d0,  1d0], [3, 8])
  ! 2-point Gauss abscissa, 1/sqrt(3); the weights are 1
  double precision, parameter :: gp = 0.5773502691896258d0

  double precision :: e, nu, alpha, eta0, cz, cond, rho, cp, qflag
  double precision :: g, bk, eta, fac, dvol, po, pn, zold, ssum, dz
  double precision :: xi(3), shp(8), dshp(3, 8), dxdxi(3, 3), dxidx(3, 3), dndx(3, 8), detj
  double precision :: bmat(6, 24), dmat(6, 6), deps(6), sold(6), snew(6), sdev(6), dsdt(6)
  double precision :: tgp, toldgp, dtgp, phigp, q, gradt(3), w
  double precision :: db(6, 24)
  integer :: ig, jg, kg, igp, ia, ib, i, j, iu, ju, it, jt, base

  e = props(1); nu = props(2); alpha = props(3); eta0 = props(4); cz = props(5)
  cond = props(6); rho = props(7); cp = props(8); qflag = props(9)

  g = e / (2d0 * (1d0 + nu))
  bk = e / (3d0 * (1d0 - 2d0 * nu))

  rhs(1:ndofel, 1) = 0d0
  amatrx = 0d0

  igp = 0
  do kg = 1, 2
  do jg = 1, 2
  do ig = 1, 2
    igp = igp + 1
    xi = [merge(-gp, gp, ig == 1), merge(-gp, gp, jg == 1), merge(-gp, gp, kg == 1)]

    ! trilinear shape functions and their reference derivatives
    do ia = 1, 8
      shp(ia) = 0.125d0 * (1d0 + xin(1, ia) * xi(1)) * (1d0 + xin(2, ia) * xi(2)) &
                * (1d0 + xin(3, ia) * xi(3))
      dshp(1, ia) = 0.125d0 * xin(1, ia) * (1d0 + xin(2, ia) * xi(2)) * (1d0 + xin(3, ia) * xi(3))
      dshp(2, ia) = 0.125d0 * xin(2, ia) * (1d0 + xin(1, ia) * xi(1)) * (1d0 + xin(3, ia) * xi(3))
      dshp(3, ia) = 0.125d0 * xin(3, ia) * (1d0 + xin(1, ia) * xi(1)) * (1d0 + xin(2, ia) * xi(2))
    end do

    ! dxdxi(i, j) = d x_i / d xi_j
    dxdxi = matmul(coords(1:3, 1:8), transpose(dshp))
    call inv3(dxdxi, dxidx, detj)
    ! dN/dx_i = sum_j dN/dxi_j * dxi_j/dx_i
    dndx = matmul(transpose(dxidx), dshp)
    w = detj

    ! strain-displacement matrix, engineering shear strains (xx yy zz xy xz yz)
    bmat = 0d0
    do ia = 1, 8
      iu = 3 * (ia - 1)
      bmat(1, iu + 1) = dndx(1, ia)
      bmat(2, iu + 2) = dndx(2, ia)
      bmat(3, iu + 3) = dndx(3, ia)
      bmat(4, iu + 1) = dndx(2, ia); bmat(4, iu + 2) = dndx(1, ia)
      bmat(5, iu + 1) = dndx(3, ia); bmat(5, iu + 3) = dndx(1, ia)
      bmat(6, iu + 2) = dndx(3, ia); bmat(6, iu + 3) = dndx(2, ia)
    end do

    ! temperature, its increment and phi at the Gauss point
    tgp = 0d0; dtgp = 0d0; phigp = 0d0; gradt = 0d0
    do ia = 1, 8
      it = 4 * ia
      tgp = tgp + shp(ia) * u(it)
      dtgp = dtgp + shp(ia) * du(it, 1)
      gradt = gradt + dndx(:, ia) * u(it)
      if (npredf >= 1) phigp = phigp + shp(ia) * (predef(1, 1, ia) + predef(2, 1, ia))
    end do
    toldgp = tgp - dtgp

    ! mechanical strain increment (tensor shear components)
    deps = 0d0
    do ia = 1, 8
      do i = 1, 3
        iu = 4 * (ia - 1) + i
        do j = 1, 6
          deps(j) = deps(j) + bmat(j, 3 * (ia - 1) + i) * du(iu, 1)
        end do
      end do
    end do
    deps(1:3) = deps(1:3) - alpha * dtgp
    deps(4:6) = 0.5d0 * deps(4:6)
    dvol = deps(1) + deps(2) + deps(3)

    ! Maxwell update from the converged state of the previous increment
    base = nsv * (igp - 1)
    sold = svars(base + 1:base + 6)
    zold = svars(base + 7)
    eta = eta0 * (1d0 + cz * zold)
    fac = 1d0 / (1d0 + g * dtime / eta)
    po = (sold(1) + sold(2) + sold(3)) / 3d0
    pn = po + bk * dvol
    do i = 1, 3
      sdev(i) = fac * (sold(i) - po + 2d0 * g * (deps(i) - dvol / 3d0))
    end do
    do i = 4, 6
      sdev(i) = fac * (sold(i) + 2d0 * g * deps(i))
    end do
    snew(1:3) = sdev(1:3) + pn
    snew(4:6) = sdev(4:6)
    ssum = sdev(1)**2 + sdev(2)**2 + sdev(3)**2 + 2d0 * (sdev(4)**2 + sdev(5)**2 + sdev(6)**2)
    dz = sqrt(2d0 / 3d0 * ssum) * dtime / (2d0 * eta)
    svars(base + 1:base + 6) = snew
    svars(base + 7) = zold + dz

    ! tangent at fixed Z (engineering shear) and d(stress)/dT
    dmat = 0d0
    do i = 1, 3
      do j = 1, 3
        dmat(i, j) = bk - 2d0 * g * fac / 3d0
      end do
      dmat(i, i) = dmat(i, i) + 2d0 * g * fac
    end do
    do i = 4, 6
      dmat(i, i) = g * fac
    end do
    dsdt = 0d0
    dsdt(1:3) = -3d0 * bk * alpha

    q = qflag * phigp**2
    db = matmul(dmat, bmat)

    do ia = 1, 8
      ! mechanics: internal force and its derivatives
      do i = 1, 3
        iu = 4 * (ia - 1) + i
        rhs(iu, 1) = rhs(iu, 1) - w * dot_product(bmat(:, 3 * (ia - 1) + i), snew)
        do ib = 1, 8
          do j = 1, 3
            ju = 4 * (ib - 1) + j
            amatrx(iu, ju) = amatrx(iu, ju) &
                             + w * dot_product(bmat(:, 3 * (ia - 1) + i), db(:, 3 * (ib - 1) + j))
          end do
          jt = 4 * ib
          amatrx(iu, jt) = amatrx(iu, jt) &
                           + w * dot_product(bmat(:, 3 * (ia - 1) + i), dsdt) * shp(ib)
        end do
      end do

      ! heat: capacity, conduction and source; nothing here depends on u
      it = 4 * ia
      rhs(it, 1) = rhs(it, 1) - w * (shp(ia) * rho * cp * (tgp - toldgp) / dtime &
                                     + cond * dot_product(dndx(:, ia), gradt) - shp(ia) * q)
      do ib = 1, 8
        jt = 4 * ib
        amatrx(it, jt) = amatrx(it, jt) + w * (shp(ia) * shp(ib) * rho * cp / dtime &
                                               + cond * dot_product(dndx(:, ia), dndx(:, ib)))
      end do
    end do
  end do
  end do
  end do

contains

  subroutine inv3(m, minv, det)
    double precision, intent(in) :: m(3, 3)
    double precision, intent(out) :: minv(3, 3), det
    det = m(1, 1) * (m(2, 2) * m(3, 3) - m(2, 3) * m(3, 2)) &
        - m(1, 2) * (m(2, 1) * m(3, 3) - m(2, 3) * m(3, 1)) &
        + m(1, 3) * (m(2, 1) * m(3, 2) - m(2, 2) * m(3, 1))
    minv(1, 1) = (m(2, 2) * m(3, 3) - m(2, 3) * m(3, 2)) / det
    minv(1, 2) = (m(1, 3) * m(3, 2) - m(1, 2) * m(3, 3)) / det
    minv(1, 3) = (m(1, 2) * m(2, 3) - m(1, 3) * m(2, 2)) / det
    minv(2, 1) = (m(2, 3) * m(3, 1) - m(2, 1) * m(3, 3)) / det
    minv(2, 2) = (m(1, 1) * m(3, 3) - m(1, 3) * m(3, 1)) / det
    minv(2, 3) = (m(1, 3) * m(2, 1) - m(1, 1) * m(2, 3)) / det
    minv(3, 1) = (m(2, 1) * m(3, 2) - m(2, 2) * m(3, 1)) / det
    minv(3, 2) = (m(1, 2) * m(3, 1) - m(1, 1) * m(3, 2)) / det
    minv(3, 3) = (m(1, 1) * m(2, 2) - m(1, 2) * m(2, 1)) / det
  end subroutine inv3

end subroutine uel
