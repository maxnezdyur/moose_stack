! Probe UEL: a scalar diffusion HEX8 that prints PREDEF field 1 at node 1 of element 1
subroutine uel(rhs, amatrx, svars, energy, ndofel, nrhs, nsvars, props, nprops, coords, &
               mcrd, nnode, u, du, v, a, jtype, time, dtime, kstep, kinc, jelem, params, &
               ndload, jdltyp, adlmag, predef, npredf, lflags, mlvarx, ddlmag, mdload, &
               pnewdt, jprops, njprop, period)
  implicit none
  integer :: ndofel, nrhs, nsvars, nprops, mcrd, nnode, jtype, kstep, kinc, jelem
  integer :: ndload, npredf, mlvarx, mdload, njprop, i
  integer :: jdltyp(mdload, *), lflags(*), jprops(*)
  double precision :: rhs(mlvarx, *), amatrx(ndofel, ndofel), svars(nsvars), energy(8)
  double precision :: props(nprops), coords(mcrd, nnode), u(ndofel), du(mlvarx, *)
  double precision :: v(ndofel), a(ndofel), time(2), dtime, params(*)
  double precision :: adlmag(mdload, *), predef(2, npredf, nnode), ddlmag(mdload, *)
  double precision :: pnewdt, period
  rhs(1:ndofel, 1) = 0d0
  amatrx = 0d0
  do i = 1, ndofel
    amatrx(i, i) = 1d0
    rhs(i, 1) = -u(i)
  end do
  if (jelem == 1) write(*, '(a, f8.2, a, f10.4, a, f10.4)') ' UEL call: t = ', time(2) + dtime, &
      '  PREDEF value = ', predef(1, 1, 1), '  increment = ', predef(2, 1, 1)
end subroutine uel
