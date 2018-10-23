%function to generate the Hamiltonian of the TlF ground state at given
%electric and magnetic field. The Hamiltonian comes out in parts and then
%have to sum the parts together and multiply by relevant constants, e.g.
%Ham = Ham_rot + Bz*Ham_Z_z + Ez_1*D_TlF*Ham_St_z + c3*Ham_c3 + c4*Ham_c4 + c1 * Ham_c1 + c2 * Ham_c2;

function [Ham_rot, Ham_c1, Ham_c2,Ham_c3, Ham_c4, Ham_St_z, Ham_Z_z] = make_TlF_gs_ham_new_c3(Jmax,I_Tl,I_F,QN)

N_states = (2*I_Tl+1)*(2*I_F+1)*(Jmax+1)^2;  %Total number of states in Hilbert space considered

%Initialise some of the Hamiltonian matrices
Ham_rot = zeros(N_states,N_states);
Ham_c1 = zeros(N_states,N_states);
Ham_c2 = zeros(N_states,N_states);
Ham_c3 = zeros(N_states,N_states);
Ham_c4 = zeros(N_states,N_states);


%Start loop over all states to generate H_rot, H_sr and H_ss
for i = 1:N_states  %i = row number of H matrix, corresponds to BRA <J_i,m_J_i,m_Tl_i,m_F_i|
    J_i = QN(i,1); %rotational quantum number for state #i
    m_J_i = QN(i,2); %rotational projection for state #i
    m_Tl_i = QN(i,3); %Tl projection for state #i
    m_F_i = QN(i,4); %I projection for state #i
    for j = i:N_states  % j = column number of H matrix, corresponds to KET |J_j,m_J_j,m_Tl_j,m_F_j>; indexing gives upper right part of matrix
        J_j = QN(j,1); %rotational quantum number for state #j
        m_J_j = QN(j,2); %rotational projection for state #j
        m_Tl_j = QN(j,3); %Tl projection for state #j
        m_F_j = QN(j,4); %I projection for state #j
        %
        %fill in rotational term
        %
        if j == i  %this means all quantum numbers m_F, m_Tl, m_J, and J are the same, so add rotational term
            Ham_rot(i,j) = Ham_rot(i,j)+ J_j*(J_j +1);
        end %end condition for diagonal matrix elements
        %for dot products, use the relation in terms of spin ladder ops
        %(NOT spherical tensor components...using ladder ops is just
        %a bit easier to code):  
        % A.B = AzBz + (A+B-)/2 + (A-B+)/2
        % J+|jm> = \sqrt{j(j+1)-m(m+1)}|j m+1>, 
        % J-|jm> = \sqrt{j(j+1)-m(m-1)}|j m-1>, Jz|jm> = m|jm>
        %
        % c1 term (I_Tl.J)
        if J_i == J_j && m_F_i == m_F_j %J and m_F have to match
            if m_J_i == m_J_j && m_Tl_i == m_Tl_j  %this is JzIz term.  Remember that j = ket, i = bra.
                Ham_c1(i,j) = Ham_c1(i,j)+ m_J_j*m_Tl_j;
            elseif m_J_i == m_J_j +1 && m_Tl_i == m_Tl_j -1  %this is J+I- term. Remember that j = ket, i = bra.
                Ham_c1(i,j) = Ham_c1(i,j)+ sqrt(J_j*(J_j +1)-m_J_j*(m_J_j +1))*sqrt(I_Tl*(I_Tl +1)- m_Tl_j*(m_Tl_j -1))/2;
            elseif m_J_i == m_J_j -1 && m_Tl_i == m_Tl_j +1  %this is J-I+ term. Remember that j = ket, i = bra.
                Ham_c1(i,j) = Ham_c1(i,j)+ sqrt(J_j*(J_j +1)-m_J_j*(m_J_j -1))*sqrt(I_Tl*(I_Tl +1)- m_Tl_j*(m_Tl_j +1))/2;
            end
        end %end c1 term
        % c2 term (I_F.J)
        if J_i == J_j && m_Tl_i == m_Tl_j %J and m_Tl have to match
            if m_J_i == m_J_j && m_F_i == m_F_j  %this is JzIz term
                Ham_c2(i,j) = Ham_c2(i,j)+ m_J_i*m_F_i;
            elseif m_J_i == m_J_j +1 && m_F_i == m_F_j -1  %this is J+I- term. Remember that j = ket, i = bra.
                Ham_c2(i,j) = Ham_c2(i,j)+ sqrt(J_j*(J_j +1)-m_J_j*(m_J_j +1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j -1))/2;
            elseif m_J_i == m_J_j -1 && m_F_i == m_F_j +1  %this is J-I+ term. Remember that j = ket, i = bra.
                Ham_c2(i,j) = Ham_c2(i,j)+ sqrt(J_j*(J_j +1)-m_J_j*(m_J_j -1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j +1))/2;
            end
        end %end c2 term
        
        %calculating c3 term from hamiltonian of form
        %H = c'_3*[2*I_1.I_2 - 3*(I_1.R)(I_2.R)/R^2 - 3*(I_2.R)(I_1.R)/R^2]
        %Turns out c'3 = 5*c3/2 where c3 is the constant given in Ramsey 1984
        %To evaluate matrix elements use fact that the R-terms are proportional 
        %to spherical harmonics:
        %Treat terms in Hamiltonian one-by-one after expanding by using
        % A.B = AzBz + (A+B-)/2 + (A-B+)/2
        %Expand by using A.B = AzBz + (A+B-)/2 + (A-B+)/2 and treat terms in 
        %Hamiltonian one-by-one. 
        %Note that R_{+/-}/R = (x +/- iy)/R = exp(+/-i*\phi)*sin(\theta)
        %and R_{z}/R = cos(\theta)
        
        %The relations needed to convert R-terms to spherical
        %harmonics (denote spherical harmonics as Y(l,m)):
        % R_{+/-}*R_{+/-}/R^2 = 4*sqrt(2*\pi/15)*Y(2, +/-2)
        % R_{+/-}*R_{z}/R^2 = -/+ 2*sqrt(2*\pi/15)*Y(2, +/- 1)
        % R_{-}*R_{+}/R^2 = 4*sqrt(\pi)/3 *[Y(0,0) - sqrt(1/5)*Y(2,0)
        % R_{z}*R_{z}/R^2 = 2*sqrt(\pi)/3 *[2/sqrt(5)* Y(2,0) + Y(0,0)]
        
        %Finally use formula for integral product of spherical harmonics:
        % integral{Y(l_1,m_1)*Y(l,m)*Y(l_2,m_2)*d\Omega}
        %  = sqrt((2*l+1)(2*l_2 + 1)/(4*\pi)(2*l_1 +1)) 
        %   * ClebschGordan(l,l_2,l_1,0,0,0)
        %   * ClebschGordan(l,l_2,l_1,m,m_2,m_1)
        
        %1st part of c3 term: - 3*(I_1.R)(I_2.R)/R^2 - 3*(I_2.R)(I_1.R)/R^2
        
        %1st term: [I_{1+}I_{2+}R_{-}R_{-}]/2
        if m_Tl_i == m_Tl_j + 1 && m_F_i == m_F_j + 1
            Ham_c3(i,j) = Ham_c3(i,j) -3* sqrt(2/3)...
                *sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j +1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j +1))...
                *sqrt((2*J_j+1)/(2*J_i+1))*ClebschGordan(2,J_j,J_i,0,0,0)*ClebschGordan(2,J_j,J_i,-2,m_J_j,m_J_i);
        end
        
        %2nd term: (I_{1+}*I_{2z} + I_{1z}*I_{2+}) * (R_{-}R_{z})
        if m_Tl_i == m_Tl_j + 1 && m_F_i == m_F_j %I_{1+}*I_{2z}
            Ham_c3(i,j) = Ham_c3(i,j) -3* sqrt(2/3)...
                *(sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j +1)) * m_F_j)...
                * sqrt((2*J_j+1)/(2*J_i+1)) * ClebschGordan(2,J_j,J_i,0,0,0) * ClebschGordan(2,J_j,J_i,-1,m_J_j,m_J_i);
            
        elseif m_Tl_i == m_Tl_j && m_F_i == m_F_j + 1 %I_{1z}*I_{2+}
            Ham_c3(i,j) = Ham_c3(i,j) -3* sqrt(2/3)...
                * (m_Tl_j * sqrt(I_F*(I_F +1)- m_F_j*(m_F_j +1)))...
                * sqrt((2*J_j+1)/(2*J_i+1)) * ClebschGordan(2,J_j,J_i,0,0,0) * ClebschGordan(2,J_j,J_i,-1,m_J_j,m_J_i);
        end
        
        %3rd term: [(I_{1+}*I_{2-}+I_{1-}*I_{2+})*(R_{-}R_{+})/2 +
        %I_{1z}I_{2z}R_{z}R_{z}*2]
        if m_Tl_i == m_Tl_j + 1 && m_F_i == m_F_j - 1 %I_{1+}*I_{2-}
            Ham_c3(i,j) = Ham_c3(i,j) -3 / 3 ...
                * sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j +1))* sqrt(I_F*(I_F +1)-m_F_j*(m_F_j -1)) ...
                * (sqrt((2*J_j+1)/(2*J_i+1)) * ClebschGordan(0,J_j,J_i,0,0,0) * ClebschGordan(0,J_j,J_i,0,m_J_j,m_J_i)...
                - sqrt((2*J_j+1)/(2*J_i+1)) * ClebschGordan(2,J_j,J_i,0,0,0) * ClebschGordan(2,J_j,J_i,0,m_J_j,m_J_i));
        elseif m_Tl_i == m_Tl_j - 1 && m_F_i == m_F_j + 1 %I_{1-}*I_{2+}
            Ham_c3(i,j) = Ham_c3(i,j) -3 / 3 ...
                * sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j -1))* sqrt(I_F*(I_F +1)-m_F_j*(m_F_j +1)) ...
                * (sqrt((2*J_j+1)/(2*J_i+1)) * ClebschGordan(0,J_j,J_i,0,0,0) * ClebschGordan(0,J_j,J_i,0,m_J_j,m_J_i)...
                - sqrt((2*J_j+1)/(2*J_i+1)) * ClebschGordan(2,J_j,J_i,0,0,0) * ClebschGordan(2,J_j,J_i,0,m_J_j,m_J_i));
        elseif m_Tl_i == m_Tl_j && m_F_i == m_F_j %I_{1z}I_{2z}
            Ham_c3(i,j) = Ham_c3(i,j) -3* 2/3 *m_Tl_j*m_F_j ...
                * (...
                2 * sqrt((2*J_j+1)/(2*J_i+1))* ClebschGordan(2,J_j,J_i,0,0,0) * ClebschGordan(2,J_j,J_i,0,m_J_j,m_J_i)...
                + sqrt((2*J_j+1)/(2*J_i+1)) * ClebschGordan(0,J_j,J_i,0,0,0) * ClebschGordan(0,J_j,J_i,0,m_J_j,m_J_i)...
                );
        end
        
        %4th term: [(I_{1-}*I_{2z}+I_{1z}*I_{2-})*(R_{+}R_{z})
        if m_Tl_i == m_Tl_j - 1 && m_F_i == m_F_j %I_{1-}*I_{2z}
            Ham_c3(i,j) = Ham_c3(i,j) -3*(-1)*sqrt(2/3)...
                * sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j -1))*m_F_j...
                * sqrt((2*J_j+1)/(2*J_i+1)) *ClebschGordan(2,J_j,J_i,0,0,0) *ClebschGordan(2,J_j,J_i,+1,m_J_j,m_J_i);
        elseif m_Tl_i == m_Tl_j && m_F_i == m_F_j-1 %I_{1z}*I_{2-}
            Ham_c3(i,j) = Ham_c3(i,j) -3* (m_Tl_i*sqrt(I_F*(I_F +1)-m_F_j*(m_F_j -1)))...
                *(-1)* sqrt(2/3)...
                * sqrt((2*J_j+1)/(2*J_i+1)) *ClebschGordan(2,J_j,J_i,0,0,0) *ClebschGordan(2,J_j,J_i,+1,m_J_j,m_J_i);
        end
            
        %5th term: [I_{1-}I_{2-}R_{+}R_{+}]/2
        if m_Tl_i == m_Tl_j - 1 && m_F_i == m_F_j-1 %I_{1-}I_{2-}
        Ham_c3(i,j) = Ham_c3(i,j) -3* sqrt(2/3)...
            *sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j -1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j -1))...
            *sqrt((2*J_j+1)/(2*J_i+1))*ClebschGordan(2,J_j,J_i,0,0,0)*ClebschGordan(2,J_j,J_i,+2,m_J_j,m_J_i)/2;
        end
        %1st part of c3 done
        
        %2nd part of c3 term: 2*I_1.I_2
        if J_i == J_j && m_J_i == m_J_j %J and m_J have to match
            if m_Tl_i == m_Tl_j && m_F_i == m_F_j  %this is I1zI2z term
                Ham_c3(i,j) = Ham_c3(i,j) +2*m_Tl_j*m_F_j;
            elseif m_Tl_i == m_Tl_j +1 && m_F_i == m_F_j -1  %this is I1+I2- term
                Ham_c3(i,j) = Ham_c3(i,j) +2*sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j +1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j -1))/2;
            elseif m_Tl_i == m_Tl_j -1 && m_F_i == m_F_j +1  %this is I1-I2+ term
                Ham_c3(i,j) = Ham_c3(i,j) +2*sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j -1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j +1))/2;
            end 
        end %end 2nd part of c3 term
        
        
        % c4 term c4(I_Tl.I_F)
        if J_i == J_j && m_J_i == m_J_j %J and m_J have to match
            if m_Tl_i == m_Tl_j && m_F_i == m_F_j  %this is I1zI2z term
                Ham_c4(i,j) = Ham_c4(i,j)+ m_Tl_j*m_F_j;
            elseif m_Tl_i == m_Tl_j +1 && m_F_i == m_F_j -1  %this is I1+I2- term
                Ham_c4(i,j) = Ham_c4(i,j)+ sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j +1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j -1))/2;
            elseif m_Tl_i == m_Tl_j -1 && m_F_i == m_F_j +1  %this is I1-I2+ term
                Ham_c4(i,j) = Ham_c4(i,j)+ sqrt(I_Tl*(I_Tl +1)-m_Tl_j*(m_Tl_j -1))*sqrt(I_F*(I_F +1)- m_F_j*(m_F_j +1))/2;
            end 
        end %end c4
        %symmetrize Hamiltonian matrix
        Ham_rot(j,i) = Ham_rot(i,j);
        Ham_c1(j,i) = Ham_c1(i,j);
        Ham_c2(j,i) = Ham_c2(i,j);
        Ham_c3(j,i) = Ham_c3(i,j);
        Ham_c4(j,i) = Ham_c4(i,j);
        %
    end  %end loop over index j
end  %end loop over index i
%[V,D] = eig(Ham_ff);        %find eigenvalues D and eigenvectors V of Hamiltonian
%subtract away rotational energy for easier viewing of hyperfine
%substructure
%hfs_mat = zeros(N_states,N_states);
%for i=1:N_states
    %J_i = QN(i,1);
    %hfs_mat(i,i) = D(i,i) - J_i*(J_i +1)*Brot; %subtract rotational energy
%end
%hfs_kHz = diag(hfs_mat)/1000;  %change units to kHz for easier viewing
%stem(hfs_kHz)  %plot the hfs deviations from bare rotational structure(in kHz) in a stem plot
% OK, this completes the field-free Hamiltonian.  Now construct the
% Hamiltonian matrix for the Zeeman interaction.
% H_Z = -\mu_J(J.B)/J - \mu_1(I1.B)/I1 - \mu_2(I2.B)/I2
% Constants from Wilkening et al, in Hz/Gauss, for 205Tl
mu_J = 35;
mu_Tl = 1240.5;
mu_F = 2003.63;
%
% Construct Hamiltonian independent of B to start; mutliply by B at the end
% First, include B_z term only for simplicity.
%
Ham_Z_z = zeros(N_states,N_states);
%
for i = 1:N_states
    J_i = QN(i,1); %rotational quantum number for state #i
    m_J_i = QN(i,2); %rotational projection for state #i
    m_Tl_i = QN(i,3); %Tl projection for state #i
    m_F_i = QN(i,4); %I projection for state #i
    for j = i:N_states
        J_j = QN(j,1); %rotational quantum number for state #j
        m_J_j = QN(j,2); %rotational projection for state #j
        m_Tl_j = QN(j,3); %Tl projection for state #j
        m_F_j = QN(j,4); %I projection for state #j
        if J_i == J_j %condition for all Zeeman terms to be nonzero: diagonal in J, J nonzero
            %Bz term
            if m_J_i == m_J_j && m_Tl_i == m_Tl_j && m_F_i == m_F_j  %all quantum numbers m_F, m_Tl, m_J are the same, as needed for Bz term
                Ham_Z_z(i,j) = Ham_Z_z(i,j) - mu_Tl*m_Tl_j/I_Tl - mu_F*m_F_j/I_F;  %both nuclear spin Zeeman terms
                if J_i ~= 0 %rotational Zeeman, accounting for J=0 anomalous behavior
                    Ham_Z_z(i,j) = Ham_Z_z(i,j) - mu_J*m_J_j/J_j; %rotational Zeeman, accounting for J=0 anomalous behavior
                end %end rotational Zeeman term
            end %end Bz term
        end %end condition to be diagonal in J
        %symmetrize Hamiltonian matrix
        Ham_Z_z(j,i) = Ham_Z_z(i,j);
        %
    end  %end loop over index j
end  %end loop over index i
%Bz = 3.0; %Bz in Gauss
%Ham = Ham_ff + Bz*Ham_Z_z;
%[V,D] = eig(Ham);        %find eigenvalues D and eigenvectors V of Hamiltonian
%subtract away rotational energy 
%for easier viewing of hyperfine substructure
%hfs_mat = zeros(N_states,N_states);
%for i=1:N_states
%    J_i = QN(i,1);
%    hfs_mat(i,i) = D(i,i) - J_i*(J_i +1)*Brot; %subtract rotational energy
%end
%hfs_kHz = diag(hfs_mat)/1000;  %change units to kHz for easier viewing
%stem(hfs_kHz);  %plot the hfs deviations from bare rotational structure(in kHz) in a stem plot
%
% Now Stark Hamiltonian.
% As for Zeeman, first construct Hamiltonian idependent of E, then multiply
% by E at the end.
%
% molecular dipole moment D_TlF = 4.2282 Debye = 4.2282 * 0.393430307 ea_0
% D_TlF = 4.2282 * 0.393430307 *5.291772e-9 e.cm 
% so D_TlF * (Electric field in V/cm) is
% D_TlF*E[V/cm] = 4.2282 * 0.393430307 *5.291772e-9 * E[V/cm] eV 
% D_TlF*E[V/cm] = 4.2282 * 0.393430307 *5.291772e-9/4.135667e-15 *E[V/cm] Hz
% 

% Include only E_z term.
%
Ham_St_z = zeros(N_states,N_states);
%
for i = 1:N_states
    J_i = QN(i,1); %rotational quantum number for state #i
    m_J_i = QN(i,2); %rotational projection for state #i
    m_Tl_i = QN(i,3); %Tl projection for state #i
    m_F_i = QN(i,4); %I projection for state #i
    for j = i:N_states
        J_j = QN(j,1); %rotational quantum number for state #j
        m_J_j = QN(j,2); %rotational projection for state #j
        m_Tl_j = QN(j,3); %Tl projection for state #j
        m_F_j = QN(j,4); %I projection for state #j
        %
        %  Stark Hamiltonian matrix elements must be diagonal in m_Tl and m_F,
        %  and have J' = J \pm 1.
        %  For E_z, also must be diagonal in m_J.
        %  For m_J = 0, <J \pm 1,0|H_St|j,0> given in J. Petricka thesis:
        %  = -dEz(J)/sqrt((2J-1)(2J+1)) [J' = J-1]
        %  = -dEz(J+1)/sqrt((2J+1)(2J+3)) [J' = J+1]
        %  For m_J \neq 0, get matrix element from Wigner-Eckhart theorem.
        %  This is worked out in detail in document
        %  "General form of rotational Stark matrix elements.docx"
        %  <J \pm 1,m|H_St|j,m>
        %  = -dEz sqrt( (J^2-m^2)/(4J^2-1) ) [J'=J-1]
        %  = -dEz sqrt( ((J+1)^2 - m^2)/(4(J+1)^2-1) ) [J'=J+1]
        %
        if m_F_i == m_F_j && m_Tl_i == m_Tl_j && m_J_i == m_J_j  %this ensures terms diagonal in m_F, m_Tl, and m_J
            if J_i == J_j -1
                Ham_St_z(i,j) = Ham_St_z(i,j) - sqrt((J_j^2-m_J_j^2)/(4*J_j^2 -1));
            elseif J_i == J_j +1
                Ham_St_z(i,j) = Ham_St_z(i,j) - sqrt(((J_j+1)^2-m_J_j^2)/(4*(J_j+1)^2 -1));
            end
        end
        %
        %symmetrize Hamiltonian matrix
        Ham_St_z(j,i) = Ham_St_z(i,j);
        %
    end  %end loop over index j
end  %end loop over index i

